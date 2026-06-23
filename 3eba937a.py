import json
import os
import re
import sys
import time
import uuid
import webbrowser
from contextlib import contextmanager
from datetime import datetime
from html import escape
from urllib.parse import quote
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

APP_NAME = "Agri Clinic Solan"
PRINT_SUBTITLE = "Diagnostic Slip"
POLL_MS = 3000
LOCK_FILE = ".agriclinic.lock"
STATUS_UNSEEN = "unseen"
STATUS_SEEN = "seen"
STATUS_APPROVED = "approved"
STATUS_COLORS = {
    STATUS_UNSEEN: "#fff3a6",
    STATUS_SEEN: "#cfe4ff",
    STATUS_APPROVED: "#cfeecf",
}
LOCATIONS = ["YSN", "Solan"]
COUNTRY_CODES = ["+91", "+1", "+44", "+61", "+971", "+977", "+880"]
PLEASE_NOTE_TEXT = """Please Note: The above recommendations are based on the tests of the samples submitted by the concerned farmer(s). Agriclinic DSC takes no responsibility of any deleterious outcome arising out of any faulty sampling and usage of pesticide or fertilizers or other Agro-chemicals whatsoever. NOT FOR AGRI LEGAL PURPOSE

While every care is taken to ensure the results from analysis are as accurate as possible. It is important to note that analysis relates to the sample received by Agri Clinic Solan, and is representative only of that sample. No warranty is given by the Agri Clinic that the results from analysis relates to any part of a field or growing area not covered by the sample received. It is important to ensure that any diagnostic, soil, leaf, silage of fruit samples sent to this lab for analysis is representative of the entire held requiring analysis and that samples are obtained in accordance with the established sampling techniques"""
DEFAULT_LISTS = {
    "problems": ["Nematode", "Leaf blight", "Root rot", "Nutrient deficiency", "Leaf curl"],
    "concerns": ["Low yield", "Yellowing leaves", "Poor germination", "Pest pressure", "Fruit drop"],
    "symptoms": ["Wilting", "Leaf spots", "Stunted growth", "Stem discoloration", "Root damage"],
    "solutions": ["Field inspection", "Improve drainage", "Spray schedule", "Lab follow-up", "Soil amendment"],
}
UI_SIZES = {
    "small": {"base": 9, "title": 12, "section": 10, "pad": 6, "list": 6, "text_h": 4},
    "medium": {"base": 10, "title": 14, "section": 11, "pad": 8, "list": 7, "text_h": 5},
    "large": {"base": 12, "title": 17, "section": 13, "pad": 10, "list": 9, "text_h": 6},
}


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_text():
    return datetime.now().strftime("%Y-%m-%d")


def normalize_text(value):
    return " ".join(str(value or "").strip().split())


def sanitize_name(value):
    value = normalize_text(value)
    value = re.sub(r'[\\/:*?"<>|]+', '', value)
    value = value.replace("\n", " ")
    return value[:80] or "Unnamed"


def digits_only(value):
    return "".join(ch for ch in str(value) if ch.isdigit())


def slug_for_whatsapp(code, phone):
    code_digits = digits_only(code)
    phone_digits = digits_only(phone)
    if not phone_digits:
        return ""
    if code_digits == "91" and len(phone_digits) == 10:
        return f"91{phone_digits}"
    if phone_digits.startswith(code_digits):
        return phone_digits
    return f"{code_digits}{phone_digits}"


class DataStore:
    def __init__(self, root_folder):
        self.set_root(root_folder)

    def set_root(self, root_folder):
        self.root = os.path.abspath(root_folder)
        self.cases_dir = os.path.join(self.root, "cases")
        self.lists_dir = os.path.join(self.root, "master_lists")
        os.makedirs(self.cases_dir, exist_ok=True)
        os.makedirs(self.lists_dir, exist_ok=True)
        self.lock_path = os.path.join(self.root, LOCK_FILE)
        self._ensure_lists()

    def _ensure_lists(self):
        for kind, items in DEFAULT_LISTS.items():
            path = self.list_path(kind)
            if not os.path.exists(path):
                self._write_json(path, {"items": items})

    def list_path(self, kind):
        return os.path.join(self.lists_dir, f"{kind}.json")

    def _read_json(self, path, fallback):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return fallback

    def _write_json(self, path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    @contextmanager
    def lock(self, timeout=10):
        start = time.time()
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.close(fd)
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.lock_path) > 40:
                        os.remove(self.lock_path)
                        continue
                except OSError:
                    pass
                if time.time() - start > timeout:
                    raise TimeoutError("Another PC is saving right now. Please wait a few seconds and try again.")
                time.sleep(0.25)
        try:
            yield
        finally:
            try:
                os.remove(self.lock_path)
            except OSError:
                pass

    def load_list(self, kind):
        data = self._read_json(self.list_path(kind), {"items": []})
        items = []
        seen = set()
        for raw in data.get("items", []):
            item = normalize_text(raw)
            if not item:
                continue
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                items.append(item)
        return sorted(items, key=str.casefold)

    def save_list(self, kind, items):
        cleaned = []
        seen = set()
        for raw in items:
            item = normalize_text(raw)
            if not item:
                continue
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                cleaned.append(item)
        cleaned.sort(key=str.casefold)
        with self.lock():
            self._write_json(self.list_path(kind), {"items": cleaned})
        return cleaned

    def next_folder_name(self, date_folder, name, phone):
        os.makedirs(date_folder, exist_ok=True)
        nums = []
        for item in os.listdir(date_folder):
            match = re.match(r"^(\d+)\.", item)
            if match:
                nums.append(int(match.group(1)))
        next_num = max(nums, default=0) + 1
        return f"{next_num}. {sanitize_name(name)} {digits_only(phone) or 'no-number'}"

    def case_folder_abs(self, case_folder_rel):
        return os.path.join(self.cases_dir, case_folder_rel)

    def save_case(self, record):
        with self.lock():
            if not record.get("case_folder"):
                day = record.get("created_date") or today_text()
                day_folder = os.path.join(self.cases_dir, day)
                folder_name = self.next_folder_name(day_folder, record.get("name"), record.get("phone"))
                record["case_folder"] = os.path.join(day, folder_name)
                record["created_date"] = day
            folder = self.case_folder_abs(record["case_folder"])
            os.makedirs(folder, exist_ok=True)
            self._write_json(os.path.join(folder, "case.json"), record)
            self.write_print_html(record)
            self.write_print_text(record)

    def load_cases(self):
        cases = []
        if not os.path.exists(self.cases_dir):
            return cases
        for root, _dirs, files in os.walk(self.cases_dir):
            if "case.json" in files:
                record = self._read_json(os.path.join(root, "case.json"), None)
                if record:
                    cases.append(record)
        cases.sort(key=lambda r: (r.get("updated_at", ""), r.get("name", "")), reverse=True)
        return cases

    def find_case(self, case_id):
        for record in self.load_cases():
            if record.get("id") == case_id:
                return record
        return None

    def write_print_text(self, record):
        folder = self.case_folder_abs(record["case_folder"])
        lines = [
            APP_NAME,
            PRINT_SUBTITLE,
            "=" * 60,
            f"Location: {record.get('location', '')}",
            f"Name: {record.get('name', '')}",
            f"Phone: {record.get('country_code', '+91')} {record.get('phone', '')}",
            f"Address: {record.get('village', '')}, PO {record.get('po', '')}, {record.get('district', '')}, {record.get('state', '')} - {record.get('pin_code', '')}",
            f"Crop: {record.get('crop_name', '')}",
            f"Status: {record.get('status', '')}",
            "",
            f"Concerns: {', '.join(record.get('concerns', [])) or '-'}",
            f"Symptoms: {', '.join(record.get('symptoms', [])) or '-'}",
            f"Problems: {', '.join(record.get('problems', [])) or '-'}",
            f"Solutions: {', '.join(record.get('solutions', [])) or '-'}",
            f"Medicines: {record.get('medicines', '') or '-'}",
            f"Instructions: {record.get('instructions', '') or '-'}",
            "",
            "Tests:",
            f"Upright microscopy: {'Yes' if record.get('upright_microscopy') else 'No'}",
            f"Stethoscopic microscopy: {'Yes' if record.get('stethoscopic_microscopy') else 'No'}",
            f"Bacterial ooze / slime test: {'Yes' if record.get('bacterial_ooze_test') else 'No'}",
            "",
            PLEASE_NOTE_TEXT,
        ]
        with open(os.path.join(folder, "print_view.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def logo_path(self):
        candidates = [
            os.path.join(self.root, "print_logo.png"),
            os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "print_logo.png"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    def write_print_html(self, record):
        folder = self.case_folder_abs(record["case_folder"])
        logo_tag = ""
        logo = self.logo_path()
        if logo:
            logo_uri = "file:///" + logo.replace('\\', '/')
            logo_tag = f'<div class="logo-wrap"><img src="{logo_uri}" alt="logo"></div>'
        tests = [
            ("Upright microscopy", record.get("upright_microscopy")),
            ("Stethoscopic microscopy", record.get("stethoscopic_microscopy")),
            ("Bacterial ooze / slime test", record.get("bacterial_ooze_test")),
        ]
        def row(label, value):
            return f"<tr><th>{escape(label)}</th><td>{escape(value or '-')}</td></tr>"
        def list_or_dash(values):
            return ", ".join(values) if values else "-"
        test_html = "".join(
            f'<li><span class="box">{"✓" if ok else ""}</span>{escape(label)}</li>' for label, ok in tests
        )
        html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(record.get('name', 'Slip'))}</title>
<style>
body {{ font-family: Arial, sans-serif; color: #202020; margin: 24px; }}
.wrap {{ max-width: 860px; margin: 0 auto; border: 2px solid #333; padding: 18px 22px; }}
.top {{ text-align: center; border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 14px; }}
.logo-wrap img {{ max-height: 90px; margin: 0 auto 8px; }}
h1 {{ margin: 0; font-size: 26px; }}
.subtitle {{ font-size: 16px; font-weight: 700; margin-top: 6px; letter-spacing: 0.5px; }}
.grid {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
.grid th, .grid td {{ border: 1px solid #666; padding: 8px 10px; vertical-align: top; text-align: left; }}
.grid th {{ width: 26%; background: #f3f3f3; }}
.section {{ margin-top: 14px; }}
.section h2 {{ font-size: 16px; margin: 0 0 6px; border-bottom: 1px solid #999; padding-bottom: 4px; }}
.note {{ margin-top: 16px; font-size: 12px; line-height: 1.45; border-top: 2px solid #333; padding-top: 10px; white-space: pre-line; }}
.checks {{ list-style: none; padding: 0; margin: 0; }}
.checks li {{ margin: 6px 0; }}
.box {{ display: inline-block; width: 18px; height: 18px; border: 1px solid #333; text-align: center; line-height: 18px; margin-right: 8px; font-weight: 700; }}
.printbar {{ margin: 10px 0 18px; text-align: right; }}
@media print {{ .printbar {{ display: none; }} body {{ margin: 0; }} .wrap {{ border: none; }} }}
</style>
</head>
<body>
<div class="printbar"><button onclick="window.print()">Print</button></div>
<div class="wrap">
<div class="top">
{logo_tag}
<h1>{escape(APP_NAME)}</h1>
<div class="subtitle">{escape(PRINT_SUBTITLE)}</div>
</div>
<table class="grid">
{row('Location', record.get('location', ''))}
{row('Customer name', record.get('name', ''))}
{row('Phone', f"{record.get('country_code', '+91')} {record.get('phone', '')}")}
{row('Village', record.get('village', ''))}
{row('Post office', record.get('po', ''))}
{row('District', record.get('district', ''))}
{row('Pin code', record.get('pin_code', ''))}
{row('State', record.get('state', ''))}
{row('Crop', record.get('crop_name', ''))}
{row('Status', record.get('status', '').title())}
{row('Concerns', list_or_dash(record.get('concerns', [])))}
{row('Symptoms', list_or_dash(record.get('symptoms', [])))}
{row('Problems', list_or_dash(record.get('problems', [])))}
{row('Solutions', list_or_dash(record.get('solutions', [])))}
{row('Medicines', record.get('medicines', ''))}
{row('Instructions', record.get('instructions', ''))}
</table>
<div class="section">
<h2>Tests</h2>
<ul class="checks">{test_html}</ul>
</div>
<div class="note">{escape(PLEASE_NOTE_TEXT)}</div>
</div>
</body>
</html>"""
        with open(os.path.join(folder, "print_view.html"), "w", encoding="utf-8") as f:
            f.write(html)


class ScrollableFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vbar.set)
        self.vbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_frame)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class SmartField(ttk.LabelFrame):
    def __init__(self, master, title, kind, store, allow_manage=True):
        super().__init__(master, text=title, padding=8)
        self.kind = kind
        self.store = store
        self.allow_manage = allow_manage
        self.query_var = tk.StringVar()
        self.options = self.store.load_list(kind)
        self.selected = []
        self._build()
        self.refresh_matches()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))
        ttk.Entry(top, textvariable=self.query_var).pack(side="left", fill="x", expand=True)
        self.query_var.trace_add("write", lambda *_: self.refresh_matches())
        ttk.Button(top, text="Add typed", command=self.add_typed).pack(side="left", padx=(6, 0))
        if self.allow_manage:
            ttk.Button(top, text="Manage list", command=self.manage_list).pack(side="left", padx=(6, 0))
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Matches").pack(anchor="w")
        self.match_list = tk.Listbox(left, height=6, exportselection=False)
        self.match_list.pack(fill="both", expand=True)
        self.match_list.bind("<Double-Button-1>", lambda _e: self.add_from_match())
        mid = ttk.Frame(body)
        mid.pack(side="left", fill="y", padx=6)
        ttk.Button(mid, text="Add →", command=self.add_from_match).pack(fill="x", pady=(20, 6))
        ttk.Button(mid, text="← Remove", command=self.remove_selected).pack(fill="x")
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Selected").pack(anchor="w")
        self.selected_list = tk.Listbox(right, height=6, exportselection=False)
        self.selected_list.pack(fill="both", expand=True)

    def refresh_options(self):
        self.options = self.store.load_list(self.kind)
        self.refresh_matches()

    def refresh_matches(self):
        q = normalize_text(self.query_var.get()).casefold()
        starts, contains = [], []
        for item in self.options:
            test = item.casefold()
            if not q:
                starts.append(item)
            elif test.startswith(q):
                starts.append(item)
            elif q in test:
                contains.append(item)
        self.match_list.delete(0, tk.END)
        for item in starts + contains:
            self.match_list.insert(tk.END, item)

    def render_selected(self):
        self.selected_list.delete(0, tk.END)
        for item in self.selected:
            self.selected_list.insert(tk.END, item)

    def add_item(self, value):
        item = normalize_text(value)
        if not item:
            return
        option_keys = {x.casefold() for x in self.options}
        selected_keys = {x.casefold() for x in self.selected}
        if item.casefold() not in option_keys:
            self.options.append(item)
            self.options = self.store.save_list(self.kind, self.options)
        if item.casefold() not in selected_keys:
            self.selected.append(item)
            self.selected.sort(key=str.casefold)
        self.render_selected()
        self.query_var.set("")
        self.refresh_matches()

    def add_typed(self):
        self.add_item(self.query_var.get())

    def add_from_match(self):
        cur = self.match_list.curselection()
        if not cur:
            self.add_typed()
            return
        self.add_item(self.match_list.get(cur[0]))

    def remove_selected(self):
        cur = self.selected_list.curselection()
        if not cur:
            return
        del self.selected[cur[0]]
        self.render_selected()

    def get(self):
        return list(self.selected)

    def set(self, values):
        seen = set()
        cleaned = []
        for raw in values or []:
            item = normalize_text(raw)
            if not item:
                continue
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                cleaned.append(item)
                if key not in {x.casefold() for x in self.options}:
                    self.options.append(item)
        self.options = self.store.save_list(self.kind, self.options)
        self.selected = sorted(cleaned, key=str.casefold)
        self.render_selected()
        self.refresh_matches()

    def manage_list(self):
        win = tk.Toplevel(self)
        win.title(f"Manage {self.kind.title()}")
        win.geometry("420x420")
        holder = ttk.Frame(win, padding=10)
        holder.pack(fill="both", expand=True)
        lb = tk.Listbox(holder)
        lb.pack(fill="both", expand=True)
        for item in self.store.load_list(self.kind):
            lb.insert(tk.END, item)
        row = ttk.Frame(holder)
        row.pack(fill="x", pady=(8, 0))
        new_var = tk.StringVar()
        ttk.Entry(row, textvariable=new_var).pack(side="left", fill="x", expand=True)
        def add():
            item = normalize_text(new_var.get())
            if item:
                current = [lb.get(i) for i in range(lb.size())]
                if item.casefold() not in {x.casefold() for x in current}:
                    current.append(item)
                    current.sort(key=str.casefold)
                    lb.delete(0, tk.END)
                    for c in current:
                        lb.insert(tk.END, c)
            new_var.set("")
        def delete():
            cur = lb.curselection()
            if cur:
                lb.delete(cur[0])
        ttk.Button(row, text="Add", command=add).pack(side="left", padx=(6,0))
        ttk.Button(row, text="Delete selected", command=delete).pack(side="left", padx=(6,0))
        def save_close():
            items = [lb.get(i) for i in range(lb.size())]
            self.options = self.store.save_list(self.kind, items)
            self.refresh_matches()
            win.destroy()
        ttk.Button(holder, text="Save", command=save_close).pack(anchor="e", pady=(8, 0))


class FrontDeskForm(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.current_id = None
        self.current_case_folder = None
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="-")
        self.location_var = tk.StringVar(value=LOCATIONS[0])
        self.country_code_var = tk.StringVar(value="+91")
        self.name_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.village_var = tk.StringVar()
        self.po_var = tk.StringVar()
        self.district_var = tk.StringVar()
        self.pin_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.crop_var = tk.StringVar()
        self.build()

    def build(self):
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=8)
        paned.add(left, weight=2)
        paned.add(right, weight=3)
        self.build_list(left)
        self.build_form(right)

    def build_list(self, parent):
        ttk.Label(parent, text="Front Desk Cases", style="Title.TLabel").pack(anchor="w", pady=(0,6))
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0,6))
        ttk.Label(top, text="Search").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<KeyRelease>", lambda _e: self.refresh_list())
        cols = ("status", "location", "name", "phone", "updated")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings")
        for col, width in [("status", 75), ("location", 70), ("name", 150), ("phone", 100), ("updated", 135)]:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.load_selected())
        for key, color in STATUS_COLORS.items():
            self.tree.tag_configure(key, background=color)

    def build_form(self, parent):
        ttk.Label(parent, text="Front Desk Intake", style="Title.TLabel").pack(anchor="w", pady=(0,6))
        scroll = ScrollableFrame(parent)
        scroll.pack(fill="both", expand=True)
        form = scroll.inner
        basic = ttk.LabelFrame(form, text="Customer details", padding=8)
        basic.pack(fill="x", pady=(0,8))
        ttk.Label(basic, text="Location").grid(row=0, column=0, sticky="w")
        ttk.Combobox(basic, textvariable=self.location_var, values=LOCATIONS, state="readonly", width=10).grid(row=1, column=0, sticky="ew", padx=(0,8))
        ttk.Label(basic, text="Name").grid(row=0, column=1, sticky="w")
        ttk.Entry(basic, textvariable=self.name_var).grid(row=1, column=1, sticky="ew", padx=(0,8))
        ttk.Label(basic, text="Phone").grid(row=0, column=2, sticky="w")
        phone_wrap = ttk.Frame(basic)
        phone_wrap.grid(row=1, column=2, sticky="ew")
        ttk.Combobox(phone_wrap, textvariable=self.country_code_var, values=COUNTRY_CODES, width=6, state="readonly").pack(side="left")
        ttk.Entry(phone_wrap, textvariable=self.phone_var).pack(side="left", fill="x", expand=True, padx=(6,0))
        for col in range(3):
            basic.columnconfigure(col, weight=1)
        addr = ttk.LabelFrame(form, text="Address", padding=8)
        addr.pack(fill="x", pady=(0,8))
        labels = [
            ("Village", self.village_var), ("Post Office (PO)", self.po_var), ("District", self.district_var),
            ("Pin Code", self.pin_var), ("State", self.state_var), ("Crop Name", self.crop_var)
        ]
        for i, (label, var) in enumerate(labels):
            r = (i // 3) * 2
            c = i % 3
            ttk.Label(addr, text=label).grid(row=r, column=c, sticky="w")
            ttk.Entry(addr, textvariable=var).grid(row=r+1, column=c, sticky="ew", padx=(0,8), pady=(0,6))
        for c in range(3):
            addr.columnconfigure(c, weight=1)
        self.concerns = SmartField(form, "Concerns", "concerns", self.app.store)
        self.concerns.pack(fill="x", pady=(0,8))
        self.symptoms = SmartField(form, "Symptoms", "symptoms", self.app.store)
        self.symptoms.pack(fill="x", pady=(0,8))
        read = ttk.LabelFrame(form, text="Master terminal updates", padding=8)
        read.pack(fill="both", expand=True, pady=(0,8))
        ttk.Label(read, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Label(read, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(read, text="Problems").grid(row=1, column=0, sticky="nw", pady=(8,0))
        self.rd_problems = tk.Text(read, height=3, wrap="word")
        self.rd_problems.grid(row=1, column=1, sticky="ew", pady=(8,0))
        ttk.Label(read, text="Solutions").grid(row=2, column=0, sticky="nw", pady=(8,0))
        self.rd_solutions = tk.Text(read, height=3, wrap="word")
        self.rd_solutions.grid(row=2, column=1, sticky="ew", pady=(8,0))
        ttk.Label(read, text="Medicines").grid(row=3, column=0, sticky="nw", pady=(8,0))
        self.rd_medicines = tk.Text(read, height=4, wrap="word")
        self.rd_medicines.grid(row=3, column=1, sticky="ew", pady=(8,0))
        ttk.Label(read, text="Instructions").grid(row=4, column=0, sticky="nw", pady=(8,0))
        self.rd_instructions = tk.Text(read, height=4, wrap="word")
        self.rd_instructions.grid(row=4, column=1, sticky="ew", pady=(8,0))
        read.columnconfigure(1, weight=1)
        for widget in [self.rd_problems, self.rd_solutions, self.rd_medicines, self.rd_instructions]:
            widget.configure(state="disabled")
        btns = ttk.Frame(form)
        btns.pack(fill="x")
        ttk.Button(btns, text="New", command=self.clear_form).pack(side="left")
        ttk.Button(btns, text="Save Intake", command=self.save_frontdesk).pack(side="left", padx=6)
        ttk.Button(btns, text="Open Print View", command=lambda: self.app.open_print_for(self.current_id)).pack(side="left")
        ttk.Button(btns, text="WhatsApp", command=lambda: self.app.open_whatsapp_for(self.current_id)).pack(side="left", padx=6)

    def set_readonly_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def refresh_list(self):
        data = self.app.filtered_cases(self.search_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in data:
            self.tree.insert(
                "", tk.END, iid=record["id"], tags=(record.get("status", STATUS_UNSEEN),),
                values=(record.get("status", "").title(), record.get("location", ""), record.get("name", ""), record.get("phone", ""), record.get("updated_at", ""))
            )

    def load_selected(self):
        cur = self.tree.selection()
        if not cur:
            return
        record = self.app.case_map.get(cur[0])
        if not record:
            return
        self.current_id = record.get("id")
        self.current_case_folder = record.get("case_folder")
        self.location_var.set(record.get("location", LOCATIONS[0]))
        self.country_code_var.set(record.get("country_code", "+91"))
        self.name_var.set(record.get("name", ""))
        self.phone_var.set(record.get("phone", ""))
        self.village_var.set(record.get("village", ""))
        self.po_var.set(record.get("po", ""))
        self.district_var.set(record.get("district", ""))
        self.pin_var.set(record.get("pin_code", ""))
        self.state_var.set(record.get("state", ""))
        self.crop_var.set(record.get("crop_name", ""))
        self.concerns.set(record.get("concerns", []))
        self.symptoms.set(record.get("symptoms", []))
        self.status_var.set(record.get("status", "").title())
        self.set_readonly_text(self.rd_problems, ", ".join(record.get("problems", [])) or "-")
        self.set_readonly_text(self.rd_solutions, ", ".join(record.get("solutions", [])) or "-")
        self.set_readonly_text(self.rd_medicines, record.get("medicines", "") or "-")
        self.set_readonly_text(self.rd_instructions, record.get("instructions", "") or "-")

    def clear_form(self):
        self.current_id = None
        self.current_case_folder = None
        self.location_var.set(LOCATIONS[0])
        self.country_code_var.set("+91")
        for var in [self.name_var, self.phone_var, self.village_var, self.po_var, self.district_var, self.pin_var, self.state_var, self.crop_var]:
            var.set("")
        self.concerns.set([])
        self.symptoms.set([])
        self.status_var.set("-")
        for w in [self.rd_problems, self.rd_solutions, self.rd_medicines, self.rd_instructions]:
            self.set_readonly_text(w, "")

    def build_record(self, prior=None):
        name = normalize_text(self.name_var.get())
        phone = normalize_text(self.phone_var.get())
        if not name:
            messagebox.showwarning(APP_NAME, "Please enter the customer name.")
            return None
        if not phone:
            messagebox.showwarning(APP_NAME, "Please enter the phone number.")
            return None
        prior = prior or {}
        record = {
            "id": prior.get("id") or str(uuid.uuid4()),
            "case_folder": prior.get("case_folder"),
            "created_date": prior.get("created_date") or today_text(),
            "created_at": prior.get("created_at") or now_text(),
            "updated_at": now_text(),
            "updated_by_role": "frontdesk",
            "updated_by_location": self.location_var.get(),
            "location": self.location_var.get(),
            "country_code": self.country_code_var.get(),
            "name": name,
            "phone": phone,
            "village": normalize_text(self.village_var.get()),
            "po": normalize_text(self.po_var.get()),
            "district": normalize_text(self.district_var.get()),
            "pin_code": normalize_text(self.pin_var.get()),
            "state": normalize_text(self.state_var.get()),
            "crop_name": normalize_text(self.crop_var.get()),
            "concerns": self.concerns.get(),
            "symptoms": self.symptoms.get(),
            "problems": prior.get("problems", []),
            "solutions": prior.get("solutions", []),
            "medicines": prior.get("medicines", ""),
            "instructions": prior.get("instructions", ""),
            "upright_microscopy": bool(prior.get("upright_microscopy")),
            "stethoscopic_microscopy": bool(prior.get("stethoscopic_microscopy")),
            "bacterial_ooze_test": bool(prior.get("bacterial_ooze_test")),
            "status": STATUS_UNSEEN,
            "seen_at": prior.get("seen_at", ""),
            "approved_at": "",
        }
        return record

    def save_frontdesk(self):
        prior = self.app.case_map.get(self.current_id) if self.current_id else None
        record = self.build_record(prior)
        if not record:
            return
        try:
            self.app.store.save_case(record)
            self.current_id = record["id"]
            self.current_case_folder = record["case_folder"]
            self.app.reload_cases(select_id=self.current_id)
            self.status_var.set(record["status"].title())
            messagebox.showinfo(APP_NAME, "Front desk record saved.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save record.\n\n{exc}")


class MasterForm(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.current_id = None
        self.current_case_folder = None
        self.search_var = tk.StringVar()
        self.location_var = tk.StringVar()
        self.country_code_var = tk.StringVar(value="+91")
        self.name_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.village_var = tk.StringVar()
        self.po_var = tk.StringVar()
        self.district_var = tk.StringVar()
        self.pin_var = tk.StringVar()
        self.state_var = tk.StringVar()
        self.crop_var = tk.StringVar()
        self.status_var = tk.StringVar(value="-")
        self.upright_var = tk.BooleanVar()
        self.stetho_var = tk.BooleanVar()
        self.bacterial_var = tk.BooleanVar()
        self.build()

    def build(self):
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=8)
        paned.add(left, weight=2)
        paned.add(right, weight=4)
        self.build_list(left)
        self.build_form(right)

    def build_list(self, parent):
        ttk.Label(parent, text="Master Terminal", style="Title.TLabel").pack(anchor="w", pady=(0,6))
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0,6))
        ttk.Label(top, text="Search").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<KeyRelease>", lambda _e: self.refresh_list())
        cols = ("status", "location", "name", "phone", "crop", "updated")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings")
        widths = {"status":80, "location":70, "name":150, "phone":100, "crop":110, "updated":135}
        for col in cols:
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=widths[col], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.load_selected(mark_seen=True))
        for key, color in STATUS_COLORS.items():
            self.tree.tag_configure(key, background=color)

    def build_form(self, parent):
        ttk.Label(parent, text="Master Review Form", style="Title.TLabel").pack(anchor="w", pady=(0,6))
        scroll = ScrollableFrame(parent)
        scroll.pack(fill="both", expand=True)
        form = scroll.inner
        info = ttk.LabelFrame(form, text="Case overview", padding=8)
        info.pack(fill="x", pady=(0,8))
        ttk.Label(info, text="Status").grid(row=0, column=0, sticky="w")
        ttk.Label(info, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(info, text="Location").grid(row=1, column=0, sticky="w")
        ttk.Entry(info, textvariable=self.location_var).grid(row=1, column=1, sticky="ew")
        ttk.Label(info, text="Name").grid(row=2, column=0, sticky="w")
        ttk.Entry(info, textvariable=self.name_var).grid(row=2, column=1, sticky="ew")
        ttk.Label(info, text="Phone").grid(row=3, column=0, sticky="w")
        phone_wrap = ttk.Frame(info)
        phone_wrap.grid(row=3, column=1, sticky="ew")
        ttk.Combobox(phone_wrap, textvariable=self.country_code_var, values=COUNTRY_CODES, width=6, state="readonly").pack(side="left")
        ttk.Entry(phone_wrap, textvariable=self.phone_var).pack(side="left", fill="x", expand=True, padx=(6,0))
        ttk.Label(info, text="Village / PO / District / Pin / State").grid(row=4, column=0, sticky="nw", pady=(6,0))
        addr_box = ttk.Frame(info)
        addr_box.grid(row=4, column=1, sticky="ew", pady=(6,0))
        ttk.Entry(addr_box, textvariable=self.village_var).pack(fill="x", pady=(0,4))
        ttk.Entry(addr_box, textvariable=self.po_var).pack(fill="x", pady=(0,4))
        ttk.Entry(addr_box, textvariable=self.district_var).pack(fill="x", pady=(0,4))
        ttk.Entry(addr_box, textvariable=self.pin_var).pack(fill="x", pady=(0,4))
        ttk.Entry(addr_box, textvariable=self.state_var).pack(fill="x")
        ttk.Label(info, text="Crop").grid(row=5, column=0, sticky="w", pady=(6,0))
        ttk.Entry(info, textvariable=self.crop_var).grid(row=5, column=1, sticky="ew", pady=(6,0))
        info.columnconfigure(1, weight=1)
        self.concerns = SmartField(form, "Concerns", "concerns", self.app.store)
        self.concerns.pack(fill="x", pady=(0,8))
        self.symptoms = SmartField(form, "Symptoms", "symptoms", self.app.store)
        self.symptoms.pack(fill="x", pady=(0,8))
        self.problems = SmartField(form, "Problems", "problems", self.app.store)
        self.problems.pack(fill="x", pady=(0,8))
        self.solutions = SmartField(form, "Solutions", "solutions", self.app.store)
        self.solutions.pack(fill="x", pady=(0,8))
        test = ttk.LabelFrame(form, text="Tests", padding=8)
        test.pack(fill="x", pady=(0,8))
        ttk.Checkbutton(test, text="Upright microscopy", variable=self.upright_var).pack(anchor="w")
        ttk.Checkbutton(test, text="Stethoscopic microscopy", variable=self.stetho_var).pack(anchor="w")
        ttk.Checkbutton(test, text="Bacterial ooze / slime test", variable=self.bacterial_var).pack(anchor="w")
        meds = ttk.LabelFrame(form, text="Medicines required", padding=8)
        meds.pack(fill="both", expand=True, pady=(0,8))
        self.medicines_text = tk.Text(meds, height=5, wrap="word")
        self.medicines_text.pack(fill="both", expand=True)
        inst = ttk.LabelFrame(form, text="Instructions for customer", padding=8)
        inst.pack(fill="both", expand=True, pady=(0,8))
        self.instructions_text = tk.Text(inst, height=5, wrap="word")
        self.instructions_text.pack(fill="both", expand=True)
        btns = ttk.Frame(form)
        btns.pack(fill="x")
        ttk.Button(btns, text="Save Seen", command=self.save_seen).pack(side="left")
        ttk.Button(btns, text="Approve & Save", command=self.save_approved).pack(side="left", padx=6)
        ttk.Button(btns, text="Open Print View", command=lambda: self.app.open_print_for(self.current_id)).pack(side="left")
        ttk.Button(btns, text="WhatsApp", command=lambda: self.app.open_whatsapp_for(self.current_id)).pack(side="left", padx=6)

    def refresh_list(self):
        data = self.app.filtered_cases(self.search_var.get())
        for item in self.tree.get_children():
            self.tree.delete(item)
        for record in data:
            self.tree.insert(
                "", tk.END, iid=record["id"], tags=(record.get("status", STATUS_UNSEEN),),
                values=(record.get("status", "").title(), record.get("location", ""), record.get("name", ""), record.get("phone", ""), record.get("crop_name", ""), record.get("updated_at", ""))
            )

    def load_selected(self, mark_seen=False):
        cur = self.tree.selection()
        if not cur:
            return
        record = self.app.case_map.get(cur[0])
        if not record:
            return
        if mark_seen and record.get("status") == STATUS_UNSEEN:
            record["status"] = STATUS_SEEN
            record["seen_at"] = now_text()
            record["updated_at"] = now_text()
            record["updated_by_role"] = "master"
            self.app.store.save_case(record)
            self.app.reload_cases(select_id=record["id"])
            record = self.app.case_map.get(cur[0], record)
        self.current_id = record.get("id")
        self.current_case_folder = record.get("case_folder")
        self.status_var.set(record.get("status", "").title())
        self.location_var.set(record.get("location", ""))
        self.country_code_var.set(record.get("country_code", "+91"))
        self.name_var.set(record.get("name", ""))
        self.phone_var.set(record.get("phone", ""))
        self.village_var.set(record.get("village", ""))
        self.po_var.set(record.get("po", ""))
        self.district_var.set(record.get("district", ""))
        self.pin_var.set(record.get("pin_code", ""))
        self.state_var.set(record.get("state", ""))
        self.crop_var.set(record.get("crop_name", ""))
        self.concerns.set(record.get("concerns", []))
        self.symptoms.set(record.get("symptoms", []))
        self.problems.set(record.get("problems", []))
        self.solutions.set(record.get("solutions", []))
        self.upright_var.set(bool(record.get("upright_microscopy")))
        self.stetho_var.set(bool(record.get("stethoscopic_microscopy")))
        self.bacterial_var.set(bool(record.get("bacterial_ooze_test")))
        self.medicines_text.delete("1.0", tk.END)
        self.medicines_text.insert("1.0", record.get("medicines", ""))
        self.instructions_text.delete("1.0", tk.END)
        self.instructions_text.insert("1.0", record.get("instructions", ""))

    def build_record(self, status):
        prior = self.app.case_map.get(self.current_id)
        if not prior:
            messagebox.showwarning(APP_NAME, "Select a case first in Master Terminal.")
            return None
        record = dict(prior)
        record.update({
            "updated_at": now_text(),
            "updated_by_role": "master",
            "location": normalize_text(self.location_var.get()),
            "country_code": self.country_code_var.get(),
            "name": normalize_text(self.name_var.get()),
            "phone": normalize_text(self.phone_var.get()),
            "village": normalize_text(self.village_var.get()),
            "po": normalize_text(self.po_var.get()),
            "district": normalize_text(self.district_var.get()),
            "pin_code": normalize_text(self.pin_var.get()),
            "state": normalize_text(self.state_var.get()),
            "crop_name": normalize_text(self.crop_var.get()),
            "concerns": self.concerns.get(),
            "symptoms": self.symptoms.get(),
            "problems": self.problems.get(),
            "solutions": self.solutions.get(),
            "medicines": self.medicines_text.get("1.0", "end").strip(),
            "instructions": self.instructions_text.get("1.0", "end").strip(),
            "upright_microscopy": self.upright_var.get(),
            "stethoscopic_microscopy": self.stetho_var.get(),
            "bacterial_ooze_test": self.bacterial_var.get(),
            "status": status,
            "seen_at": prior.get("seen_at") or now_text(),
            "approved_at": now_text() if status == STATUS_APPROVED else prior.get("approved_at", ""),
        })
        return record

    def save_seen(self):
        record = self.build_record(STATUS_SEEN)
        if not record:
            return
        try:
            self.app.store.save_case(record)
            self.app.reload_cases(select_id=record["id"])
            self.status_var.set("Seen")
            messagebox.showinfo(APP_NAME, "Case saved as seen.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save case.\n\n{exc}")

    def save_approved(self):
        record = self.build_record(STATUS_APPROVED)
        if not record:
            return
        try:
            self.app.store.save_case(record)
            self.app.reload_cases(select_id=record["id"])
            self.status_var.set("Approved")
            messagebox.showinfo(APP_NAME, "Case approved and saved.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not approve case.\n\n{exc}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} - Shared Workflow")
        self.geometry("1480x900")
        self.minsize(1100, 720)
        self.case_map = {}
        self.ui_size = "medium"
        self.store = DataStore(self.default_root())
        self.folder_var = tk.StringVar(value=self.store.root)
        self.build_menu()
        self.configure_styles()
        self.build_ui()
        self.reload_cases()
        self.start_polling()

    def default_root(self):
        return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "shared_data")

    def build_menu(self):
        menu = tk.Menu(self)
        self.config(menu=menu)
        settings = tk.Menu(menu, tearoff=0)
        menu.add_cascade(label="Settings", menu=settings)
        settings.add_command(label="Change shared folder", command=self.change_folder)
        size_menu = tk.Menu(settings, tearoff=0)
        settings.add_cascade(label="UI size", menu=size_menu)
        size_menu.add_command(label="Small", command=lambda: self.apply_ui_size("small"))
        size_menu.add_command(label="Medium", command=lambda: self.apply_ui_size("medium"))
        size_menu.add_command(label="Large", command=lambda: self.apply_ui_size("large"))
        settings.add_separator()
        settings.add_command(label="Reload now", command=self.reload_cases)

    def configure_styles(self):
        self.style = ttk.Style(self)
        self.apply_ui_size(self.ui_size)

    def apply_ui_size(self, size_name):
        self.ui_size = size_name
        cfg = UI_SIZES[size_name]
        default_font = tkfont.nametofont("TkDefaultFont")
        text_font = tkfont.nametofont("TkTextFont")
        heading_font = tkfont.nametofont("TkHeadingFont")
        for f in [default_font, text_font]:
            f.configure(size=cfg["base"])
        heading_font.configure(size=cfg["title"], weight="bold")
        self.style.configure("TLabel", font=("Segoe UI", cfg["base"]))
        self.style.configure("TButton", font=("Segoe UI", cfg["base"]))
        self.style.configure("TEntry", font=("Segoe UI", cfg["base"]))
        self.style.configure("TCombobox", font=("Segoe UI", cfg["base"]))
        self.style.configure("Treeview", font=("Segoe UI", cfg["base"]), rowheight=max(24, cfg["base"] * 2 + 6))
        self.style.configure("Treeview.Heading", font=("Segoe UI", cfg["base"], "bold"))
        self.style.configure("TLabelframe.Label", font=("Segoe UI", cfg["section"], "bold"))
        self.style.configure("Title.TLabel", font=("Segoe UI", cfg["title"], "bold"))
        self.style.configure("Status.TLabel", font=("Segoe UI", cfg["section"], "bold"))

    def build_ui(self):
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0,6))
        ttk.Label(top, text="Shared folder:", style="Title.TLabel").pack(side="left")
        ttk.Entry(top, textvariable=self.folder_var, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Change folder", command=self.change_folder).pack(side="left")
        ttk.Button(top, text="Reload", command=self.reload_cases).pack(side="left", padx=(6,0))
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self.front = FrontDeskForm(self.notebook, self)
        self.master_form = MasterForm(self.notebook, self)
        self.notebook.add(self.front, text="Front Desk")
        self.notebook.add(self.master_form, text="Master Terminal")

    def change_folder(self):
        folder = filedialog.askdirectory(title="Choose shared folder", initialdir=self.store.root)
        if not folder:
            return
        try:
            self.store.set_root(folder)
            self.folder_var.set(self.store.root)
            self.reload_cases()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not use that folder.\n\n{exc}")

    def filtered_cases(self, query=""):
        q = normalize_text(query).casefold()
        data = list(self.case_map.values())
        if not q:
            return sorted(data, key=lambda r: r.get("updated_at", ""), reverse=True)
        out = []
        for record in data:
            hay = " | ".join([
                record.get("status", ""), record.get("location", ""), record.get("name", ""), record.get("phone", ""),
                record.get("village", ""), record.get("district", ""), record.get("crop_name", ""),
                ", ".join(record.get("concerns", [])), ", ".join(record.get("symptoms", [])),
                ", ".join(record.get("problems", [])), record.get("medicines", ""), record.get("instructions", "")
            ]).casefold()
            if q in hay:
                out.append(record)
        return sorted(out, key=lambda r: r.get("updated_at", ""), reverse=True)

    def reload_cases(self, select_id=None):
        try:
            cases = self.store.load_cases()
            self.case_map = {r["id"]: r for r in cases if r.get("id")}
            self.front.concerns.refresh_options()
            self.front.symptoms.refresh_options()
            self.master_form.concerns.refresh_options()
            self.master_form.symptoms.refresh_options()
            self.master_form.problems.refresh_options()
            self.master_form.solutions.refresh_options()
            self.front.refresh_list()
            self.master_form.refresh_list()
            if select_id:
                for tree in [self.front.tree, self.master_form.tree]:
                    if tree.exists(select_id) if hasattr(tree, 'exists') else False:
                        pass
                for tree in [self.front.tree, self.master_form.tree]:
                    try:
                        tree.selection_set(select_id)
                    except tk.TclError:
                        continue
                if self.front.current_id == select_id:
                    self.front.load_selected()
                if self.master_form.current_id == select_id:
                    self.master_form.load_selected(mark_seen=False)
        except Exception:
            pass

    def start_polling(self):
        def tick():
            self.reload_cases()
            self.after(POLL_MS, tick)
        self.after(POLL_MS, tick)

    def open_print_for(self, case_id):
        if not case_id:
            messagebox.showinfo(APP_NAME, "Select a case first.")
            return
        record = self.case_map.get(case_id)
        if not record:
            messagebox.showinfo(APP_NAME, "Case not found.")
            return
        self.store.write_print_html(record)
        path = os.path.join(self.store.case_folder_abs(record["case_folder"]), "print_view.html")
        webbrowser.open("file:///" + path.replace('\\', '/'))

    def open_whatsapp_for(self, case_id):
        if not case_id:
            messagebox.showinfo(APP_NAME, "Select a case first.")
            return
        record = self.case_map.get(case_id)
        if not record:
            messagebox.showinfo(APP_NAME, "Case not found.")
            return
        phone = slug_for_whatsapp(record.get("country_code", "+91"), record.get("phone", ""))
        if not phone:
            messagebox.showwarning(APP_NAME, "Phone number is missing.")
            return
        summary = [
            f"{APP_NAME} - {PRINT_SUBTITLE}",
            f"Name: {record.get('name', '')}",
            f"Location: {record.get('location', '')}",
            f"Crop: {record.get('crop_name', '')}",
            f"Status: {record.get('status', '').title()}",
            f"Problems: {', '.join(record.get('problems', [])) or '-'}",
            f"Solutions: {', '.join(record.get('solutions', [])) or '-'}",
            f"Medicines: {record.get('medicines', '') or '-'}",
            f"Instructions: {record.get('instructions', '') or '-'}",
        ]
        url = f"https://wa.me/{phone}?text={quote(chr(10).join(summary))}"
        webbrowser.open(url)


if __name__ == "__main__":
    app = App()
    app.mainloop()
