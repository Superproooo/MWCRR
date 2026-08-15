#!/usr/bin/env python3
"""
My Winter Car — carparts.txt Repair Tool
Adapted to the actual binary/serialized structure of the supplied carparts.txt.

Important:
- carparts.txt is NOT ordinary text despite its .txt extension.
- WEA is stored as a little-endian IEEE-754 float and represents wear/condition.
- In the supplied file, WEA values are in the 0..100 range; 100 = top condition.
- The program edits only the 4-byte WEA value, preserving the rest of the file byte-for-byte.
"""

import os
import re
import struct
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

DEFAULT_DIR = os.path.expandvars(
    r"%USERPROFILE%\AppData\LocalLow\Amistech\My Winter Car"
)

# Names that are explicitly identifiable as engine-related in carparts.txt.
ENGINE_PREFIXES = (
    b"FANBELT", b"SPRKPLUG", b"ALTERNATOR", b"FUELPUMP",
    b"CARB", b"GEARBOX", b"FLYWHEEL", b"RADIATOR",
    b"EXHAUST", b"RACE", b"ENGINE", b"PISTON", b"CYL",
    b"CRANK", b"CAM", b"VALVE", b"OIL", b"WATERPUMP",
    b"CLUTCH", b"STARTER",
)

# Serialization marker immediately before the 4-byte WEA float in this save format.
WEA_MARKER = b"\x00\x00\x00\xffk\xd7>n"

# A serialized field starts with {~ + one-byte name length + ASCII name.
FIELD_RE = re.compile(rb"\{~([\x00-\xff])")

def find_carparts():
    p = os.path.join(DEFAULT_DIR, "carparts.txt")
    return p if os.path.isfile(p) else ""

def backup(path):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dst = f"{path}.backup_{stamp}"
    shutil.copy2(path, dst)
    return dst

def parse_wea(data):
    """Parse WEA fields from the actual MWC carparts serialization."""
    entries = []
    marker = b"\x00\x00\x00\xffk\xd7>n"

    pos = 0
    while True:
        s = data.find(b"{~", pos)
        if s < 0 or s + 3 > len(data):
            break

        name_len = data[s + 2]
        name_start = s + 3
        name_end = name_start + name_len

        if name_end > len(data):
            pos = s + 2
            continue

        name = data[name_start:name_end]

        # Serialized field names are followed by a newline.
        if name_end >= len(data) or data[name_end:name_end + 1] != b"\n":
            pos = s + 2
            continue

        if not name.endswith(b"WEA"):
            pos = name_end + 1
            continue

        marker_pos = name_end + 1
        if data[marker_pos:marker_pos + len(marker)] != marker:
            pos = name_end + 1
            continue

        value_pos = marker_pos + len(marker)
        if value_pos + 4 > len(data):
            break

        value = struct.unpack_from("<f", data, value_pos)[0]

        entries.append({
            "name": name.decode("ascii", "replace"),
            "value": value,
            "offset": value_pos,
            "name_end": name_end,
        })

        pos = value_pos + 4

    return entries

def is_engine(name):
    raw = name.encode("ascii", "ignore")
    return raw.startswith(ENGINE_PREFIXES)

def repair(data, entries, mode):
    out = bytearray(data)
    changed = 0

    for e in entries:
        if mode == "engine" and not is_engine(e["name"]):
            continue

        # WEA is a 0..100 condition value in this save format.
        if abs(e["value"] - 99.0) < 0.00001:
            continue

        struct.pack_into("<f", out, e["offset"], 99.0)
        changed += 1

    return bytes(out), changed

class App:
    def __init__(self, root):
        self.root = root
        root.title("My Winter Car — Rivett Repair Tool")
        root.geometry("850x560")
        root.minsize(760, 500)

        self.path = tk.StringVar(value=find_carparts())
        self.status = tk.StringVar(value="Выбери carparts.txt или нажми «Найти сейв».")

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="MY WINTER CAR — RIVETT REPAIR TOOL",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text="Адаптировано под реальную бинарную структуру твоего carparts.txt",
            foreground="#555"
        ).pack(anchor="w", pady=(2, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        ttk.Entry(row, textvariable=self.path).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="Обзор", command=self.browse).pack(side="left", padx=5)
        ttk.Button(row, text="Найти сейв", command=self.auto_find).pack(side="left")

        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=8)

        cols = ("name", "value", "kind", "offset")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=17)
        self.tree.heading("name", text="Деталь / поле")
        self.tree.heading("value", text="Износ / состояние")
        self.tree.heading("kind", text="Категория")
        self.tree.heading("offset", text="Offset")

        self.tree.column("name", width=270)
        self.tree.column("value", width=130)
        self.tree.column("kind", width=150)
        self.tree.column("offset", width=100)
        self.tree.pack(fill="both", expand=True)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=10)

        ttk.Button(
            buttons, text="🔎 Сканировать WEA", command=self.scan
        ).pack(side="left")

        ttk.Button(
            buttons, text="🔧 Восстановить двигатель",
            command=lambda: self.do_repair("engine")
        ).pack(side="left", padx=5)

        ttk.Button(
            buttons, text="🛠 Восстановить ВСЕ детали",
            command=lambda: self.do_repair("all")
        ).pack(side="left")

        ttk.Label(
            frame,
            text="Игра должна быть полностью закрыта. Перед изменением создаётся backup.",
            foreground="#666"
        ).pack(anchor="w")

        if self.path.get():
            self.scan()

    def browse(self):
        p = filedialog.askopenfilename(
            title="Выбери carparts.txt",
            filetypes=[
                ("carparts.txt", "carparts.txt"),
                ("TXT", "*.txt"),
                ("Все файлы", "*.*")
            ]
        )
        if p:
            self.path.set(p)
            self.scan()

    def auto_find(self):
        p = find_carparts()
        if p:
            self.path.set(p)
            self.scan()
        else:
            messagebox.showwarning(
                "Сейв не найден",
                "Автоматически carparts.txt не найден.\n"
                "Выбери его через «Обзор»."
            )

    def load(self):
        p = self.path.get().strip()
        if not os.path.isfile(p):
            raise FileNotFoundError("Указанный carparts.txt не существует.")
        return open(p, 'rb').read()

    def scan(self):
        try:
            data = self.load()
            entries = parse_wea(data)

            for item in self.tree.get_children():
                self.tree.delete(item)

            engine_count = 0
            for e in entries:
                engine = is_engine(e["name"])
                if engine:
                    engine_count += 1

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        e["name"],
                        f"{e['value']:.2f}",
                        "Двигатель" if engine else "Прочее",
                        e["offset"]
                    )
                )

            self.status.set(
                f"Найдено WEA: {len(entries)} | "
                f"явно определённых engine-полей: {engine_count}"
            )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))

    def do_repair(self, mode):
        try:
            data = self.load()
            entries = parse_wea(data)

            if not entries:
                messagebox.showwarning(
                    "WEA не найдены",
                    "В файле не обнаружены поля WEA в ожидаемом формате."
                )
                return

            candidates = [
                e for e in entries
                if mode == "all" or is_engine(e["name"])
            ]

            if not candidates:
                messagebox.showwarning(
                    "Ничего не найдено",
                    "Явно распознаваемых engine-полей WEA в этом сейве нет.\n"
                    "Можно использовать режим «Восстановить ВСЕ детали»."
                )
                return

            title = (
                "Восстановить двигатель?"
                if mode == "engine"
                else "Восстановить ВСЕ детали?"
            )

            if not messagebox.askyesno(
                title,
                f"Будет изменено полей: "
                f"{sum(abs(e['value'] - 100.0) >= 0.00001 for e in candidates)}\n\n"
                "Игра должна быть закрыта.\n"
                "Перед записью будет создан backup."
            ):
                return

            new_data, changed = repair(data, entries, mode)

            if changed == 0:
                messagebox.showinfo(
                    "Уже исправно",
                    "Все выбранные WEA уже равны 100."
                )
                return

            path = self.path.get().strip()
            b = backup(path)
            open(path, 'wb').write(new_data)

            self.scan()

            messagebox.showinfo(
                "Готово 🔧",
                f"Изменено WEA-полей: {changed}\n\n"
                f"Backup создан:\n{b}"
            )

        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
