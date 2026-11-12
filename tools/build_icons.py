# === build_icons.py ===
# Tạo web/vendor/lucide/icons.js từ bộ icon Lucide (https://lucide.dev, giấy phép ISC) - chỉ lấy các icon
# phần mềm dùng, nhúng sẵn vào file JS để chạy và build hoàn toàn offline. Chỉ cần chạy lại khi thêm icon mới:
#
#   npm pack lucide-static && tar -xzf lucide-static-*.tgz      (tải 1 lần, cần Internet)
#   python tools/build_icons.py <thư mục package/ vừa giải nén>

import json
import os
import re
import shutil
import sys

ICONS = [
    # điều hướng & thương hiệu
    "scan-text", "layout-dashboard", "scissors", "layers", "history", "cpu", "settings", "lock", "wifi-off",
    "badge-check", "hourglass", "triangle-alert", "hand", "activity",
    # thao tác chung
    "plus", "minus", "sparkles", "refresh-cw", "maximize", "frame", "square-dashed-mouse-pointer", "undo-2",
    "redo-2", "search", "save", "copy", "download", "upload", "pen-line", "arrow-left", "arrow-right",
    "arrow-up-down", "rotate-cw", "rotate-ccw", "file-plus", "replace", "trash-2", "zoom-in", "merge", "file",
    "qr-code", "cloud-upload", "folder-plus", "folder-open", "folder", "x", "play", "pause", "square", "check",
    "circle-check", "circle-x", "clock", "loader-circle", "file-text", "files", "lightbulb", "corner-down-right",
    "key-round", "import", "palette", "shield-check", "info", "brush-cleaning", "file-down", "table", "list-tree",
    "external-link", "tag", "folder-input", "chart-bar", "monitor", "chevron-down", "chevron-right",
    "chevrons-down-up", "chevrons-up-down",
    # mô hình AI
    "zap", "languages", "layout-template", "brain-circuit",
]


def main(src):
    sys.stdout.reconfigure(encoding="utf-8")
    icon_dir = os.path.join(src, "icons")
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "vendor", "lucide")
    os.makedirs(out_dir, exist_ok=True)
    version = json.load(open(os.path.join(src, "package.json"), encoding="utf-8"))["version"]
    data, missing = {}, []
    for name in ICONS:
        path = os.path.join(icon_dir, name + ".svg")
        if not os.path.exists(path):
            missing.append(name)
            continue
        svg = open(path, encoding="utf-8").read()
        inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        data[name] = re.sub(r"\s+", " ", inner).replace("> <", "><").strip()
    if missing:
        sys.exit("Không có icon: " + ", ".join(missing))
    with open(os.path.join(out_dir, "icons.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"/* Lucide icons v{version} - https://lucide.dev - ISC License (xem LICENSE cùng thư mục).\n"
                f"   Sinh tự động bởi tools/build_icons.py - không sửa tay. */\n")
        f.write("window.LUCIDE_ICONS = " + json.dumps(data, ensure_ascii=False, indent=0) + ";\n")
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(out_dir, "LICENSE"))
    print(f"Đã tạo {len(data)} icon (Lucide v{version}) -> {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "package")
