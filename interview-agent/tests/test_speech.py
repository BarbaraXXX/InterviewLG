import pytest

from interview_agent.config import SpeechSettings
from interview_agent.speech import (
    DashScopeFileSpeechTranscriber,
    DisabledSpeechTranscriber,
    OpenAICompatibleSpeechTranscriber,
    SpeechNotConfiguredError,
    SpeechTranscriptionError,
    get_speech_transcriber,
)


def test_get_speech_transcriber_selects_provider():
    assert isinstance(get_speech_transcriber(SpeechSettings(_env_file=None, provider="disabled")), DisabledSpeechTranscriber)
    assert isinstance(
        get_speech_transcriber(SpeechSettings(_env_file=None, provider="openai_compatible")),
        OpenAICompatibleSpeechTranscriber,
    )
    assert isinstance(
        get_speech_transcriber(SpeechSettings(_env_file=None, provider="dashscope_file")),
        DashScopeFileSpeechTranscriber,
    )


def test_dashscope_file_requires_oss_config():
    transcriber = DashScopeFileSpeechTranscriber(SpeechSettings(_env_file=None, provider="dashscope_file", api_key="key"))
    with pytest.raises(SpeechNotConfiguredError, match="SPEECH_OSS_ENDPOINT"):
        transcriber._transcribe_sync(b"audio", "speech.webm", "audio/webm")


def test_dashscope_file_uses_paraformer_default_for_whisper_placeholder():
    transcriber = DashScopeFileSpeechTranscriber(
        SpeechSettings(_env_file=None, provider="dashscope_file", model="whisper-1")
    )
    assert transcriber._model_name() == "paraformer-v1"


def test_dashscope_extracts_text_from_nested_result():
    transcriber = DashScopeFileSpeechTranscriber(SpeechSettings(_env_file=None, provider="dashscope_file"))
    result = {
        "status_code": 200,
        "output": {
            "results": [
                {"transcripts": [{"text": "第一段"}]},
                {"sentences": [{"text": "第二段"}]},
            ],
        },
    }

    assert transcriber._extract_text(result) == "第一段\n第二段"


def test_dashscope_failed_task_raises_clear_error():
    transcriber = DashScopeFileSpeechTranscriber(SpeechSettings(_env_file=None, provider="dashscope_file"))
    with pytest.raises(SpeechTranscriptionError, match="Invalid audio"):
        transcriber._extract_text(
            {
                "status_code": 200,
                "output": {
                    "task_id": "task-1",
                    "task_status": "FAILED",
                    "message": "Invalid audio",
                },
            }
        )


def test_dashscope_keep_temp_objects_skips_delete(monkeypatch):
    class FakeBucket:
        deleted = False

        def put_object(self, *args, **kwargs):
            return None

        def sign_url(self, *args, **kwargs):
            return "https://example.com/audio.m4a"

        def delete_object(self, *args, **kwargs):
            self.deleted = True

    class FakeOss2:
        class Auth:
            def __init__(self, *args, **kwargs):
                pass

        def __init__(self):
            self.bucket = FakeBucket()

        def Bucket(self, *args, **kwargs):
            return self.bucket

    class FakeDashscope:
        api_key = ""

    class FakeTranscription:
        @staticmethod
        def async_call(*args, **kwargs):
            return {"output": {"task_id": "task-1", "task_status": "RUNNING"}}

        @staticmethod
        def wait(*args, **kwargs):
            return {"status_code": 200, "output": {"task_status": "SUCCEEDED", "results": [{"text": "测试文本"}]}}

    fake_oss2 = FakeOss2()
    monkeypatch.setitem(__import__("sys").modules, "oss2", fake_oss2)
    monkeypatch.setitem(__import__("sys").modules, "dashscope", FakeDashscope)
    monkeypatch.setitem(
        __import__("sys").modules,
        "dashscope.audio.asr",
        type("FakeAsrModule", (), {"Transcription": FakeTranscription}),
    )

    settings = SpeechSettings(
        _env_file=None,
        provider="dashscope_file",
        api_key="key",
        oss_endpoint="oss-cn-beijing.aliyuncs.com",
        oss_bucket="bucket",
        oss_access_key_id="ak",
        oss_access_key_secret="sk",
        keep_temp_objects=True,
    )
    result = DashScopeFileSpeechTranscriber(settings)._transcribe_sync(b"audio", "speech.m4a", "audio/mp4")

    assert result.text == "测试文本"
    assert fake_oss2.bucket.deleted is False


def test_dashscope_extracts_text_from_result_url(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"transcripts": [{"text": "远程结果"}]}

    monkeypatch.setattr("interview_agent.speech.httpx.get", lambda *args, **kwargs: FakeResponse())

    transcriber = DashScopeFileSpeechTranscriber(SpeechSettings(_env_file=None, provider="dashscope_file"))
    assert transcriber._extract_text({"output": {"results": [{"transcription_url": "https://example.com/result"}]}}) == "远程结果"
