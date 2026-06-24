export function isAdminPath(pathname: string): boolean {
  return pathname === '/admin' || pathname === '/admin/login';
}
