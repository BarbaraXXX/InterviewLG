from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import uuid4

import httpx

from interview_agent.config import SpeechSettings, speech_settings

logger = logging.getLogger(__name__)


class SpeechTranscriptionError(RuntimeError):
    pass


class SpeechNotConfiguredError(SpeechTranscriptionError):
    pass


@dataclass(frozen=True)
class SpeechTranscriptionResult:
    text: str


class SpeechTranscriber:
    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> SpeechTranscriptionResult:
        raise NotImplementedError


class DisabledSpeechTranscriber(SpeechTranscriber):
    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> SpeechTranscriptionResult:
        raise SpeechNotConfiguredError("Speech transcription is not configured")


class OpenAICompatibleSpeechTranscriber(SpeechTranscriber):
    def __init__(self, settings: SpeechSettings) -> None:
        self.settings = settings

    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> SpeechTranscriptionResult:
        if not self.settings.api_key.strip():
            raise SpeechNotConfiguredError("SPEECH_API_KEY is required")

        base_url = self.settings.base_url.rstrip("/")
        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        files = {"file": (filename or "speech.webm", audio, content_type)}
        data = {"model": self.settings.model, "response_format": "json"}

        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.post(url, headers=headers, data=data, files=files)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "speech provider rejected request status=%s body=%s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            raise SpeechTranscriptionError("Speech provider rejected the request") from exc
        except httpx.HTTPError as exc:
            logger.warning("speech provider request failed: %s", exc)
            raise SpeechTranscriptionError("Speech provider request failed") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise SpeechTranscriptionError("Speech provider returned invalid JSON") from exc

        text = str(payload.get("text", "")).strip()
        if not text:
            raise SpeechTranscriptionError("Speech provider returned empty text")
        return SpeechTranscriptionResult(text=text)


class DashScopeFileSpeechTranscriber(SpeechTranscriber):
    def __init__(self, settings: SpeechSettings) -> None:
        self.settings = settings

    async def transcribe(self, audio: bytes, *, filename: str, content_type: str) -> SpeechTranscriptionResult:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._transcribe_sync, audio, filename, content_type),
                timeout=self.settings.timeout_seconds,
            )
        except TimeoutError as exc:
            raise SpeechTranscriptionError("DashScope speech transcription timed out") from exc

    def _transcribe_sync(self, audio: bytes, filename: str, content_type: str) -> SpeechTranscriptionResult:
        started_at = time.monotonic()
        if not self.settings.api_key.strip():
            raise SpeechNotConfiguredError("SPEECH_API_KEY is required")
        for key, value in {
            "SPEECH_OSS_ENDPOINT": self.settings.oss_endpoint,
            "SPEECH_OSS_BUCKET": self.settings.oss_bucket,
            "SPEECH_OSS_ACCESS_KEY_ID": self.settings.oss_access_key_id,
            "SPEECH_OSS_ACCESS_KEY_SECRET": self.settings.oss_access_key_secret,
        }.items():
            if not value.strip():
                raise SpeechNotConfiguredError(f"{key} is required for dashscope_file provider")

        try:
            logger.info("speech dashscope import start")
            import dashscope
            import oss2
            from dashscope.audio.asr import Transcription
        except ImportError as exc:
            raise SpeechNotConfiguredError("dashscope and oss2 packages are required") from exc
        logger.info("speech dashscope import done elapsed=%.2fs", time.monotonic() - started_at)

        object_key = self._build_object_key(filename)
        logger.info(
            "speech oss client init endpoint=%s bucket=%s object_key=%s",
            self._masked_endpoint(self.settings.oss_endpoint),
            self.settings.oss_bucket,
            object_key,
        )
        bucket = oss2.Bucket(
            oss2.Auth(self.settings.oss_access_key_id, self.settings.oss_access_key_secret),
            self._normalize_oss_endpoint(self.settings.oss_endpoint),
            self.settings.oss_bucket,
            connect_timeout=self.settings.timeout_seconds,
        )

        try:
            stage_started_at = time.monotonic()
            logger.info("speech oss upload start object_key=%s bytes=%d content_type=%s", object_key, len(audio), content_type)
            bucket.put_object(object_key, audio, headers={"Content-Type": content_type})
            logger.info("speech oss upload done object_key=%s elapsed=%.2fs", object_key, time.monotonic() - stage_started_at)

            stage_started_at = time.monotonic()
            logger.info("speech oss sign_url start object_key=%s expire=%ds", object_key, self.settings.oss_url_expire_seconds)
            audio_url = bucket.sign_url("GET", object_key, self.settings.oss_url_expire_seconds)
            logger.info("speech oss sign_url done object_key=%s elapsed=%.2fs", object_key, time.monotonic() - stage_started_at)

            dashscope.api_key = self.settings.api_key
            stage_started_at = time.monotonic()
            logger.info("speech dashscope async_call start model=%s object_key=%s", self._model_name(), object_key)
            response = Transcription.async_call(model=self._model_name(), file_urls=[audio_url])
            logger.info(
                "speech dashscope async_call done object_key=%s elapsed=%.2fs response_type=%s",
                object_key,
                time.monotonic() - stage_started_at,
                type(response).__name__,
            )

            stage_started_at = time.monotonic()
            logger.info("speech dashscope wait start object_key=%s", object_key)
            result = Transcription.wait(response)
            logger.info(
                "speech dashscope wait done object_key=%s elapsed=%.2fs result_type=%s",
                object_key,
                time.monotonic() - stage_started_at,
                type(result).__name__,
            )

            stage_started_at = time.monotonic()
            logger.info("speech dashscope parse start object_key=%s", object_key)
            text = self._extract_text(result)
            if not text:
                logger.warning(
                    "speech dashscope parse empty object_key=%s summary=%s",
                    object_key,
                    self._summarize_result(result),
                )
                raise SpeechTranscriptionError("DashScope returned empty text")
            logger.info(
                "speech dashscope parse done object_key=%s text_len=%d elapsed=%.2fs total=%.2fs",
                object_key,
                len(text),
                time.monotonic() - stage_started_at,
                time.monotonic() - started_at,
            )
            return SpeechTranscriptionResult(text=text)
        except SpeechTranscriptionError:
            raise
        except Exception as exc:
            logger.warning("dashscope speech transcription failed: %s", exc)
            raise SpeechTranscriptionError("DashScope speech transcription failed") from exc
        finally:
            if self.settings.keep_temp_objects:
                logger.warning(
                    "speech oss cleanup skipped by SPEECH_KEEP_TEMP_OBJECTS object_key=%s",
                    object_key,
                )
            else:
                try:
                    stage_started_at = time.monotonic()
                    logger.info("speech oss cleanup start object_key=%s", object_key)
                    bucket.delete_object(object_key)
                    logger.info(
                        "speech oss cleanup done object_key=%s elapsed=%.2fs",
                        object_key,
                        time.monotonic() - stage_started_at,
                    )
                except Exception:
                    logger.warning("failed to delete temporary speech object key=%s", object_key, exc_info=True)

    def _build_object_key(self, filename: str) -> str:
        safe_prefix = self.settings.oss_prefix.strip().strip("/") or "interview-agent/speech"
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
        if not suffix or len(suffix) > 8:
            suffix = "webm"
        return f"{safe_prefix}/{uuid4().hex}.{suffix}"

    def _model_name(self) -> str:
        model = self.settings.model.strip()
        if not model or model == "whisper-1":
            return "paraformer-v1"
        return model

    @staticmethod
    def _normalize_oss_endpoint(endpoint: str) -> str:
        endpoint = endpoint.strip()
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"https://{endpoint}"

    @staticmethod
    def _masked_endpoint(endpoint: str) -> str:
        endpoint = endpoint.strip()
        if len(endpoint) <= 12:
            return endpoint
        return f"{endpoint[:6]}...{endpoint[-6:]}"

    def _extract_text(self, result: object) -> str:
        payload = self._to_plain_data(result)
        if isinstance(payload, dict):
            if payload.get("status_code") not in (None, 200):
                message = str(payload.get("message") or payload.get("code") or "DashScope request failed")
                logger.warning("speech dashscope non-ok result summary=%s", self._summarize_result(payload))
                raise SpeechTranscriptionError(message)
            output = payload.get("output", payload)
            output_data = self._to_plain_data(output)
            if isinstance(output_data, dict):
                task_status = str(output_data.get("task_status") or "").upper()
                if task_status and task_status not in {"SUCCEEDED", "SUCCESS"}:
                    message = str(
                        output_data.get("message")
                        or output_data.get("code")
                        or payload.get("message")
                        or f"DashScope task status is {task_status}"
                    )
                    logger.warning("speech dashscope task not succeeded summary=%s", self._summarize_result(payload))
                    raise SpeechTranscriptionError(message)
            text = self._extract_text_from_output(output)
            if text:
                return text
        return ""

    def _extract_text_from_output(self, output: object) -> str:
        output = self._to_plain_data(output)
        if isinstance(output, dict):
            for key in ("transcription_url", "result_url"):
                if isinstance(output.get(key), str) and output[key].strip():
                    return self._extract_text_from_result_url(output[key].strip())
            for key in ("text", "transcription", "transcript", "sentence"):
                if isinstance(output.get(key), str) and output[key].strip():
                    return output[key].strip()
            for key in ("results", "transcripts", "sentences"):
                text = self._join_text_items(output.get(key))
                if text:
                    return text
            for key in ("task_results", "tasks"):
                text = self._join_text_items(output.get(key))
                if text:
                    return text
        return self._join_text_items(output)

    def _join_text_items(self, value: object) -> str:
        value = self._to_plain_data(value)
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                text = self._extract_text_from_output(item)
                if text:
                    parts.append(text)
            return "\n".join(parts).strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    def _extract_text_from_result_url(self, url: str) -> str:
        try:
            response = httpx.get(url, timeout=self.settings.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("failed to fetch dashscope transcription result url: %s", exc)
            raise SpeechTranscriptionError("Failed to fetch DashScope transcription result") from exc
        return self._extract_text_from_output(payload)

    @staticmethod
    def _to_plain_data(value: object) -> object:
        if isinstance(value, (dict, list, str)) or value is None:
            return value
        if isinstance(value, Mapping):
            return dict(value)
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if hasattr(value, "__dict__"):
            return vars(value)
        return value

    def _summarize_result(self, result: object) -> dict:
        payload = self._to_plain_data(result)
        if not isinstance(payload, dict):
            return {"type": type(result).__name__}
        output = self._to_plain_data(payload.get("output"))
        summary = {
            "status_code": payload.get("status_code"),
            "code": payload.get("code"),
            "message": payload.get("message"),
            "output_type": type(payload.get("output")).__name__,
        }
        if isinstance(output, dict):
            summary["output_keys"] = sorted(str(key) for key in output.keys())
            for key in ("task_id", "task_status", "code", "message"):
                if key in output:
                    summary[key] = output.get(key)
            for key in ("results", "transcripts", "sentences", "task_results"):
                if isinstance(output.get(key), list):
                    summary[f"{key}_len"] = len(output[key])
        return summary


def get_speech_transcriber(settings: SpeechSettings = speech_settings) -> SpeechTranscriber:
    provider = settings.provider.strip().lower()
    if provider in {"openai", "openai_compatible", "compatible"}:
        return OpenAICompatibleSpeechTranscriber(settings)
    if provider in {"dashscope", "dashscope_file", "aliyun"}:
        return DashScopeFileSpeechTranscriber(settings)
    return DisabledSpeechTranscriber()
