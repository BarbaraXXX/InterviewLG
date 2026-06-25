import { isAdminRoute } from './routes.ts';

export function isAdminPath(pathname: string): boolean {
  return isAdminRoute(pathname);
}
