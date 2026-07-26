/** Vietnamese số formatting: dot thousands separator, "₫" suffix. */
export function vnd(n: number): string {
  return new Intl.NumberFormat("vi-VN").format(Math.round(n));
}

export function usd(n: number): string {
  return "$" + n.toFixed(n < 1 ? 4 : 2);
}

/** Unix seconds → short relative Vietnamese label. */
export function ago(unixSeconds: number): string {
  const diff = Date.now() / 1000 - unixSeconds;
  if (diff < 60) return "vừa xong";
  if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} ngày trước`;
  return new Date(unixSeconds * 1000).toLocaleDateString("vi-VN");
}

export function timeHM(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function clock(): string {
  return new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}
