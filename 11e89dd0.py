
from __future__ import annotations

import json
import os
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from datetime import datetime
from copy import deepcopy
from html import escape

APP_TITLE = "Agri Case Prototype v2"
SETTINGS_FILE = Path("output/agri_case_prototype_v2_settings.json")
DEFAULT_SHARED_ROOT = Path("output/shared_data_v2")


def now():
    return datetime.now()


def slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip())
    return text.strip("_") or "NA"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return deepcopy(default)
    return deepcopy(default)


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def default_library():
    return {
        "concerns": [
            "Nematode concern",
            "Yellowing / chlorosis",
            "Wilting / plant death",
            "Poor growth",
            "Fruit drop",
            "Leaf spot / blight",
        ],
        "services": [
            "Soil testing",
            "Leaf testing",
            "Water testing",
            "Nematode testing",
            "Fertilizer schedule",
            "Comprehensive advisory",
        ],
        "report_types": [
            "Consultation Note",
            "Soil Report",
            "Leaf Report",
            "Water Report",
            "Nematode Report",
            "Fertilizer Schedule",
        ],
        "categories": [
            "Diagnosis pending",
            "Nematode-associated problem",
            "Soil / water-related problem",
            "Nutritional / physiological disorder",
            "Pathogen-dominated disease",
        ],
        "samples": [
            "Root",
            "Leaf",
            "Fruit",
            "Soil near plant",
            "Soil away from plant",
            "Irrigation water",
            "Nematode sample",
        ],
        "problem_templates": {
            "Nematode basic": "1. Review root condition and affected patches.\n2. Confirm crop stage and irrigation pattern.\n3. Adjust dosage and timeline before final advisory.",
            "General decline": "1. Verify drainage, irrigation and field history.\n2. Match symptom pattern with crop stage.\n3. Recheck records before final recommendation.",
        },
        "procedure_templates": {
            "Follow-up schedule": "Day 1: Start advised treatment\nDay 7: Review response\nDay 15: Recheck symptoms\nDay 30: Follow-up if needed",
        },
        "formulas": {
            "Sample dosage formula": {
                "expression": "dose_ml = area_acre * 250",
                "notes": "Placeholder formula. Replace later with your real calculation.",
            }
        },
    }


def default_settings():
    return {"shared_root": str(DEFAULT_SHARED_ROOT.resolve())}


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._sync_scroll)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind_all("<MouseWheel>", self._mousewheel, add="+")
        self.canvas.bind_all("<Up>", lambda e: self.canvas.yview_scroll(-2, "units"), add="+")
        self.canvas.bind_all("<Down>", lambda e: self.canvas.yview_scroll(2, "units"), add="+")
        self.canvas.bind_all("<Prior>", lambda e: self.canvas.yview_scroll(-8, "units"), add="+")
        self.canvas.bind_all("<Next>", lambda e: self.canvas.yview_scroll(8, "units"), add="+")

    def _sync_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)

    def _mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class CropBlock(ttk.LabelFrame):
    STAGES = ["Nursery", "Establishment", "Vegetative", "Flowering", "Fruit Set", "Harvest", "Dormancy"]

    def __init__(self, parent, app, remove_callback):
        super().__init__(parent, text="Crop")
        self.app = app
        self.remove_callback = remove_callback
        self.vars = {
            "crop_name": tk.StringVar(),
            "variety": tk.StringVar(),
            "stage": tk.StringVar(),
            "concern": tk.StringVar(),
        }
        self._build()

    def _build(self):
        pad = {"padx": 6, "pady": 4}
        for i in range(4):
            self.columnconfigure(i, weight=1)
        ttk.Label(self, text="Crop name").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.vars["crop_name"], width=24).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Variety").grid(row=0, column=2, sticky="w", **pad)
        ttk.Entry(self, textvariable=self.vars["variety"], width=24).grid(row=0, column=3, sticky="ew", **pad)
        ttk.Label(self, text="Stage").grid(row=1, column=0, sticky="w", **pad)
        ttk.Combobox(self, textvariable=self.vars["stage"], values=self.STAGES, state="readonly", width=20).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Label(self, text="Main concern").grid(row=1, column=2, sticky="w", **pad)
        ttk.Combobox(self, textvariable=self.vars["concern"], values=self.app.library["concerns"], width=20).grid(row=1, column=3, sticky="ew", **pad)
        ttk.Label(self, text="Symptoms / notes").grid(row=2, column=0, sticky="nw", **pad)
        self.symptoms = tk.Text(self, height=4, wrap="word")
        self.symptoms.grid(row=2, column=1, columnspan=3, sticky="ew", **pad)
        ttk.Button(self, text="Remove Crop", command=self.remove_callback).grid(row=0, column=4, rowspan=2, sticky="ns", padx=6, pady=4)

    def get_data(self):
        return {
            "crop_name": self.vars["crop_name"].get().strip(),
            "variety": self.vars["variety"].get().strip(),
            "stage": self.vars["stage"].get().strip(),
            "concern": self.vars["concern"].get().strip(),
            "symptoms": self.symptoms.get("1.0", "end").strip(),
        }

    def set_data(self, data):
        for key in ["crop_name", "variety", "stage", "concern"]:
            self.vars[key].set(data.get(key, ""))
        self.symptoms.delete("1.0", "end")
        self.symptoms.insert("1.0", data.get("symptoms", ""))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1450x920")
        self.minsize(1150, 720)
        self.settings = load_json(SETTINGS_FILE, default_settings())
        self.shared_root = Path(self.settings["shared_root"])
        self.library = {}
        self.customer_index = {}
        self.counters = {}
        self.selected_visit_file = None
        self.front_photo_paths = []
        self.crop_blocks = []
        self._init_storage()
        self._build_ui()
        self.load_library_ui()
        self.new_front_case()
        self.refresh_case_list()

    def _init_storage(self):
        self.shared_root.mkdir(parents=True, exist_ok=True)
        self.paths = {
            "library": self.shared_root / "library.json",
            "customer_index": self.shared_root / "customer_index.json",
            "counters": self.shared_root / "counters.json",
            "customers": self.shared_root / "customers",
            "daily_register": self.shared_root / "daily_register",
        }
        self.paths["customers"].mkdir(parents=True, exist_ok=True)
        self.paths["daily_register"].mkdir(parents=True, exist_ok=True)
        self.library = load_json(self.paths["library"], default_library())
        self.customer_index = load_json(self.paths["customer_index"], {"by_phone": {}, "next_customer_no": 1})
        self.counters = load_json(self.paths["counters"], {"visits_by_date": {}})
        save_json(self.paths["library"], self.library)
        save_json(self.paths["customer_index"], self.customer_index)
        save_json(self.paths["counters"], self.counters)

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        self.shared_label = ttk.Label(top, text=f"Shared folder: {self.shared_root}")
        self.shared_label.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="Change Shared Folder", command=self.change_shared_folder).pack(side="right", padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh_case_list).pack(side="right", padx=4)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.front_tab = ScrollableFrame(self.nb)
        self.master_tab = ttk.Frame(self.nb)
        self.library_tab = ttk.Frame(self.nb)
        self.nb.add(self.front_tab, text="Front Desk")
        self.nb.add(self.master_tab, text="Master Terminal")
        self.nb.add(self.library_tab, text="Library / Setup")

        self.build_front_tab()
        self.build_master_tab()
        self.build_library_tab()

    def reset_tabs(self):
        while self.nb.index("end"):
            self.nb.forget(0)
        self.front_tab = ScrollableFrame(self.nb)
        self.master_tab = ttk.Frame(self.nb)
        self.library_tab = ttk.Frame(self.nb)
        self.nb.add(self.front_tab, text="Front Desk")
        self.nb.add(self.master_tab, text="Master Terminal")
        self.nb.add(self.library_tab, text="Library / Setup")
        self.crop_blocks = []
        self.build_front_tab()
        self.build_master_tab()
        self.build_library_tab()
        self.load_library_ui()

    def change_shared_folder(self):
        folder = filedialog.askdirectory(title="Choose shared folder")
        if not folder:
            return
        self.settings["shared_root"] = folder
        save_json(SETTINGS_FILE, self.settings)
        self.shared_root = Path(folder)
        self.shared_label.config(text=f"Shared folder: {self.shared_root}")
        self._init_storage()
        self.reset_tabs()
        self.new_front_case()
        self.refresh_case_list()
        messagebox.showinfo("Shared Folder", "Shared folder changed.")

    def build_front_tab(self):
        f = self.front_tab.inner
        for i in range(4):
            f.columnconfigure(i, weight=1)

        self.fd = {k: tk.StringVar() for k in [
            "case_id", "reg_date", "reg_time", "mode", "registered_by", "farmer_name", "mobile", "alt_mobile",
            "whatsapp", "email", "village", "post_office", "panchayat", "tehsil", "district", "state",
            "pin_code", "preferred_language", "preferred_comm", "chief_concern", "visit_date", "visit_time", "landmark",
        ]}

        row = 0
        ttk.Label(f, text="Case Registration", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(6, 4))
        row += 1
        self._labeled_entry(f, row, 0, "Case ID", self.fd["case_id"], state="readonly")
        self._labeled_entry(f, row, 1, "Registration Date", self.fd["reg_date"], state="readonly")
        self._labeled_entry(f, row, 2, "Registration Time", self.fd["reg_time"], state="readonly")
        ttk.Label(f, text="Mode of enquiry").grid(row=row, column=3, sticky="w", padx=6, pady=4)
        ttk.Combobox(f, textvariable=self.fd["mode"], values=["Walk-in", "Telephone", "WhatsApp", "Email", "Field Visit Request", "Referral"], width=22).grid(row=row, column=3, sticky="e", padx=6, pady=4)
        row += 1
        self._labeled_entry(f, row, 0, "Registered by", self.fd["registered_by"])
        row += 1

        ttk.Label(f, text="Farmer Details", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self._labeled_entry(f, row, 0, "Farmer name", self.fd["farmer_name"])
        self._labeled_entry(f, row, 1, "Mobile", self.fd["mobile"])
        self._labeled_entry(f, row, 2, "Alternate mobile", self.fd["alt_mobile"])
        self._labeled_entry(f, row, 3, "WhatsApp", self.fd["whatsapp"])
        row += 1
        self._labeled_entry(f, row, 0, "Email", self.fd["email"])
        self._labeled_entry(f, row, 1, "Village", self.fd["village"])
        self._labeled_entry(f, row, 2, "Post office", self.fd["post_office"])
        self._labeled_entry(f, row, 3, "Panchayat", self.fd["panchayat"])
        row += 1
        self._labeled_entry(f, row, 0, "Tehsil", self.fd["tehsil"])
        self._labeled_entry(f, row, 1, "District", self.fd["district"])
        self._labeled_entry(f, row, 2, "State", self.fd["state"])
        self._labeled_entry(f, row, 3, "PIN code", self.fd["pin_code"])
        row += 1

        ttk.Label(f, text="Preferred language").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(f, textvariable=self.fd["preferred_language"], values=["Hindi", "English", "Local Dialect"], state="readonly", width=20).grid(row=row, column=0, sticky="e", padx=6, pady=4)
        ttk.Label(f, text="Preferred communication").grid(row=row, column=1, sticky="w", padx=6, pady=4)
        ttk.Combobox(f, textvariable=self.fd["preferred_comm"], values=["Call", "WhatsApp", "Email", "Printed Report"], state="readonly", width=20).grid(row=row, column=1, sticky="e", padx=6, pady=4)
        row += 1

        ttk.Label(f, text="Chief Concern", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        ttk.Label(f, text="Primary concern").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(f, textvariable=self.fd["chief_concern"], values=self.library["concerns"], width=40).grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        row += 1
        ttk.Label(f, text="Farmer's concern in own words").grid(row=row, column=0, sticky="nw", padx=6, pady=4)
        self.concern_text = tk.Text(f, height=5, wrap="word")
        self.concern_text.grid(row=row, column=1, columnspan=3, sticky="ew", padx=6, pady=4)
        row += 1

        ttk.Label(f, text="Service Request", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        sr = ttk.Frame(f)
        sr.grid(row=row, column=0, columnspan=2, sticky="w", padx=6, pady=4)
        self.service_vars = {}
        for i, item in enumerate(self.library["services"]):
            var = tk.BooleanVar(value=False)
            self.service_vars[item] = var
            ttk.Checkbutton(sr, text=item, variable=var).grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)
        ttk.Label(f, text="Requested visit date").grid(row=row, column=2, sticky="w", padx=6, pady=4)
        ttk.Entry(f, textvariable=self.fd["visit_date"], width=18).grid(row=row, column=2, sticky="e", padx=6, pady=4)
        ttk.Label(f, text="Requested visit time").grid(row=row, column=3, sticky="w", padx=6, pady=4)
        ttk.Entry(f, textvariable=self.fd["visit_time"], width=18).grid(row=row, column=3, sticky="e", padx=6, pady=4)
        row += 1
        self._labeled_entry(f, row, 0, "Landmark", self.fd["landmark"])
        row += 1

        ttk.Label(f, text="Available Material / Records", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self.material_vars = {}
        mat_frame = ttk.Frame(f)
        mat_frame.grid(row=row, column=0, columnspan=4, sticky="w", padx=6, pady=4)
        materials = ["Photographs", "Videos", "Previous lab reports", "Soil report", "Leaf report", "Water report", "Bills / labels"]
        for i, item in enumerate(materials):
            var = tk.BooleanVar(value=False)
            self.material_vars[item] = var
            ttk.Checkbutton(mat_frame, text=item, variable=var).grid(row=i // 3, column=i % 3, sticky="w", padx=6, pady=2)
        row += 1

        ttk.Label(f, text="Photos / Attachments", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        pf = ttk.Frame(f)
        pf.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
        ttk.Button(pf, text="Add Photo Files", command=self.add_photo_files).pack(side="left")
        ttk.Button(pf, text="Clear Photos", command=self.clear_photo_files).pack(side="left", padx=6)
        self.photo_label = ttk.Label(pf, text="No files selected")
        self.photo_label.pack(side="left", padx=10)
        row += 1

        ttk.Label(f, text="Crops", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        ttk.Button(f, text="Add Crop", command=self.add_crop).grid(row=row, column=3, sticky="e", padx=6, pady=4)
        row += 1
        self.crops_frame = ttk.Frame(f)
        self.crops_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
        row += 1

        action = ttk.Frame(f)
        action.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6, pady=10)
        ttk.Button(action, text="Save Intake", command=self.save_front_case).pack(side="left")
        ttk.Button(action, text="New Blank Case", command=self.new_front_case).pack(side="left", padx=6)
        ttk.Button(action, text="Open Shared Root", command=lambda: self.open_folder(self.shared_root)).pack(side="left", padx=6)

    def build_master_tab(self):
        self.master_tab.columnconfigure(1, weight=1)
        self.master_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.master_tab)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        right = ScrollableFrame(self.master_tab)
        right.grid(row=0, column=1, sticky="nsew")
        self.master_form = right.inner
        for i in range(3):
            self.master_form.columnconfigure(i, weight=1)

        ttk.Label(left, text="Cases", style="Header.TLabel").pack(anchor="w", padx=6, pady=(6, 4))
        self.case_tree = ttk.Treeview(left, columns=("status", "name", "phone", "date"), show="headings", height=28)
        for col, width in [("status", 85), ("name", 180), ("phone", 120), ("date", 95)]:
            self.case_tree.heading(col, text=col.title())
            self.case_tree.column(col, width=width, anchor="w")
        self.case_tree.pack(fill="both", expand=True, padx=6)
        self.case_tree.tag_configure("unseen", background="#fff3a3")
        self.case_tree.tag_configure("seen", background="#dcecff")
        self.case_tree.tag_configure("approved", background="#d5f0d6")

        left_btns = ttk.Frame(left)
        left_btns.pack(fill="x", padx=6, pady=6)
        ttk.Button(left_btns, text="Refresh", command=self.refresh_case_list).pack(fill="x", pady=2)
        ttk.Button(left_btns, text="Open Selected in Master", command=self.open_selected_case).pack(fill="x", pady=2)
        ttk.Button(left_btns, text="Open Visit Folder", command=self.open_selected_visit_folder).pack(fill="x", pady=2)

        self.mv = {k: tk.StringVar() for k in [
            "farmer_name", "mobile", "status", "classification", "consultant", "farm_name", "farm_location",
            "farm_area", "production_system", "farming_system", "history_when", "pattern", "soil_type",
            "drainage", "irrigation", "category", "next_action", "problem_template", "formula_name"
        ]}

        row = 0
        ttk.Label(self.master_form, text="Selected Case", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(6, 4))
        row += 1
        self._master_entry(row, 0, "Farmer name", self.mv["farmer_name"], state="readonly")
        self._master_entry(row, 1, "Mobile", self.mv["mobile"], state="readonly")
        self._master_entry(row, 2, "Status", self.mv["status"], state="readonly")
        row += 1

        ttk.Label(self.master_form, text="Farm / Field", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self._master_entry(row, 0, "Farm name", self.mv["farm_name"])
        self._master_entry(row, 1, "Farm location", self.mv["farm_location"])
        self._master_entry(row, 2, "Farm area", self.mv["farm_area"])
        row += 1
        ttk.Label(self.master_form, text="Production system").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.master_form, textvariable=self.mv["production_system"], values=["Open Field", "Orchard", "Polyhouse", "Nursery", "Shade Net", "Hydroponic"], width=22).grid(row=row, column=0, sticky="e", padx=6, pady=4)
        ttk.Label(self.master_form, text="Farming system").grid(row=row, column=1, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.master_form, textvariable=self.mv["farming_system"], values=["Conventional", "Organic", "Natural Farming", "Integrated"], width=22).grid(row=row, column=1, sticky="e", padx=6, pady=4)
        row += 1

        ttk.Label(self.master_form, text="Problem History", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self._master_entry(row, 0, "When first noticed", self.mv["history_when"])
        self._master_entry(row, 1, "Pattern", self.mv["pattern"])
        row += 1
        ttk.Label(self.master_form, text="Detailed history / remarks").grid(row=row, column=0, sticky="nw", padx=6, pady=4)
        self.history_text = tk.Text(self.master_form, height=5, wrap="word")
        self.history_text.grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        row += 1

        ttk.Label(self.master_form, text="Soil / Water Conditions", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self._master_entry(row, 0, "Soil type", self.mv["soil_type"])
        self._master_entry(row, 1, "Drainage", self.mv["drainage"])
        self._master_entry(row, 2, "Irrigation", self.mv["irrigation"])
        row += 1

        ttk.Label(self.master_form, text="Classification / Reports", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        self._master_entry(row, 0, "Case classification", self.mv["classification"])
        ttk.Label(self.master_form, text="Probable category").grid(row=row, column=1, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.master_form, textvariable=self.mv["category"], values=self.library["categories"], width=26).grid(row=row, column=1, sticky="e", padx=6, pady=4)
        self._master_entry(row, 2, "Consultant", self.mv["consultant"])
        row += 1

        self.report_vars = {}
        rf = ttk.LabelFrame(self.master_form, text="Report types")
        rf.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=4)
        for i, item in enumerate(self.library["report_types"]):
            var = tk.BooleanVar(value=False)
            self.report_vars[item] = var
            ttk.Checkbutton(rf, text=item, variable=var).grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)
        self.sample_vars = {}
        sf = ttk.LabelFrame(self.master_form, text="Samples recommended")
        sf.grid(row=row, column=2, sticky="ew", padx=6, pady=4)
        for i, item in enumerate(self.library["samples"]):
            var = tk.BooleanVar(value=False)
            self.sample_vars[item] = var
            ttk.Checkbutton(sf, text=item, variable=var).grid(row=i, column=0, sticky="w", padx=6, pady=1)
        row += 1

        ttk.Label(self.master_form, text="Templates / Recommendations", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        ttk.Label(self.master_form, text="Problem template").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        self.problem_template_box = ttk.Combobox(self.master_form, textvariable=self.mv["problem_template"], values=sorted(self.library["problem_templates"].keys()), width=28)
        self.problem_template_box.grid(row=row, column=0, sticky="e", padx=6, pady=4)
        ttk.Button(self.master_form, text="Insert Problem Template", command=self.insert_problem_template).grid(row=row, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(self.master_form, text="Formula").grid(row=row, column=2, sticky="w", padx=6, pady=4)
        self.formula_box = ttk.Combobox(self.master_form, textvariable=self.mv["formula_name"], values=sorted(self.library["formulas"].keys()), width=24)
        self.formula_box.grid(row=row, column=2, sticky="e", padx=6, pady=4)
        self.formula_box.bind("<<ComboboxSelected>>", lambda e: self.update_formula_preview())
        row += 1
        self.formula_preview = ttk.Label(self.master_form, text="Formula preview will appear here.")
        self.formula_preview.grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=4)
        row += 1
        ttk.Label(self.master_form, text="Recommendation / procedure text").grid(row=row, column=0, sticky="nw", padx=6, pady=4)
        self.recommend_text = tk.Text(self.master_form, height=10, wrap="word")
        self.recommend_text.grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        row += 1

        ttk.Label(self.master_form, text="Next Action", style="Header.TLabel").grid(row=row, column=0, sticky="w", padx=6, pady=(10, 4))
        row += 1
        ttk.Label(self.master_form, text="Next action").grid(row=row, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(self.master_form, textvariable=self.mv["next_action"], values=["Schedule field visit", "Request better samples", "Begin lab investigation", "Prepare preliminary advisory", "Await more information"], width=28).grid(row=row, column=0, sticky="e", padx=6, pady=4)
        row += 1
        ttk.Label(self.master_form, text="Consultant remarks").grid(row=row, column=0, sticky="nw", padx=6, pady=4)
        self.consult_text = tk.Text(self.master_form, height=6, wrap="word")
        self.consult_text.grid(row=row, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
        row += 1

        btns = ttk.Frame(self.master_form)
        btns.grid(row=row, column=0, columnspan=3, sticky="ew", padx=6, pady=10)
        ttk.Button(btns, text="Save Master Draft", command=self.save_master_case).pack(side="left")
        ttk.Button(btns, text="Approve & Save", command=lambda: self.save_master_case(approve=True)).pack(side="left", padx=6)
        ttk.Button(btns, text="Generate Mock Report", command=self.generate_mock_report).pack(side="left", padx=6)

    def build_library_tab(self):
        lib_nb = ttk.Notebook(self.library_tab)
        lib_nb.pack(fill="both", expand=True)

        self.lists_tab = ttk.Frame(lib_nb)
        self.templates_tab = ttk.Frame(lib_nb)
        self.formulas_tab = ttk.Frame(lib_nb)
        lib_nb.add(self.lists_tab, text="Dropdown Lists")
        lib_nb.add(self.templates_tab, text="Problem Templates")
        lib_nb.add(self.formulas_tab, text="Formulas")

        self.build_library_lists_tab()
        self.build_templates_tab()
        self.build_formulas_tab()

    def build_library_lists_tab(self):
        frm = self.lists_tab
        for i in range(4):
            frm.columnconfigure(i, weight=1)
        ttk.Label(frm, text="One item per line. Save to update dropdowns/checklists.").grid(row=0, column=0, columnspan=4, sticky="w", padx=8, pady=8)
        self.lib_concerns = self._make_text_editor(frm, 1, 0, "Concerns")
        self.lib_services = self._make_text_editor(frm, 1, 1, "Services")
        self.lib_report_types = self._make_text_editor(frm, 1, 2, "Report Types")
        self.lib_categories = self._make_text_editor(frm, 1, 3, "Categories")
        self.lib_samples = self._make_text_editor(frm, 3, 0, "Samples")
        ttk.Button(frm, text="Save Lists", command=self.save_library_lists).grid(row=5, column=0, sticky="w", padx=8, pady=10)

    def build_templates_tab(self):
        frm = self.templates_tab
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(1, weight=1)
        self.tpl_list = tk.Listbox(frm)
        self.tpl_list.grid(row=0, column=0, rowspan=4, sticky="ns", padx=8, pady=8)
        self.tpl_list.bind("<<ListboxSelect>>", lambda e: self.load_problem_template())
        self.tpl_name = tk.StringVar()
        ttk.Label(frm, text="Template name").grid(row=0, column=1, sticky="w", padx=8, pady=(8, 2))
        ttk.Entry(frm, textvariable=self.tpl_name).grid(row=0, column=1, sticky="ew", padx=8, pady=(28, 4))
        ttk.Label(frm, text="Template text").grid(row=1, column=1, sticky="nw", padx=8, pady=(8, 2))
        self.tpl_text = tk.Text(frm, height=20, wrap="word")
        self.tpl_text.grid(row=1, column=1, sticky="nsew", padx=8, pady=(28, 4))
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(btns, text="Add / Update", command=self.save_problem_template).pack(side="left")
        ttk.Button(btns, text="Delete", command=self.delete_problem_template).pack(side="left", padx=6)

    def build_formulas_tab(self):
        frm = self.formulas_tab
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(2, weight=1)
        self.formula_list = tk.Listbox(frm)
        self.formula_list.grid(row=0, column=0, rowspan=5, sticky="ns", padx=8, pady=8)
        self.formula_list.bind("<<ListboxSelect>>", lambda e: self.load_formula())
        self.form_name = tk.StringVar()
        self.form_expr = tk.StringVar()
        ttk.Label(frm, text="Formula name").grid(row=0, column=1, sticky="w", padx=8, pady=(8, 2))
        ttk.Entry(frm, textvariable=self.form_name).grid(row=0, column=1, sticky="ew", padx=8, pady=(28, 4))
        ttk.Label(frm, text="Expression").grid(row=1, column=1, sticky="w", padx=8, pady=(8, 2))
        ttk.Entry(frm, textvariable=self.form_expr).grid(row=1, column=1, sticky="ew", padx=8, pady=(28, 4))
        ttk.Label(frm, text="Notes").grid(row=2, column=1, sticky="nw", padx=8, pady=(8, 2))
        self.form_notes = tk.Text(frm, height=16, wrap="word")
        self.form_notes.grid(row=2, column=1, sticky="nsew", padx=8, pady=(28, 4))
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=1, sticky="w", padx=8, pady=8)
        ttk.Button(btns, text="Add / Update", command=self.save_formula).pack(side="left")
        ttk.Button(btns, text="Delete", command=self.delete_formula).pack(side="left", padx=6)

    def _make_text_editor(self, parent, row, col, title):
        ttk.Label(parent, text=title).grid(row=row, column=col, sticky="w", padx=8, pady=(8, 2))
        txt = tk.Text(parent, height=12, width=28)
        txt.grid(row=row + 1, column=col, sticky="nsew", padx=8, pady=4)
        return txt

    def _labeled_entry(self, parent, row, col, label, variable, state="normal"):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=6, pady=4)
        ttk.Entry(parent, textvariable=variable, state=state, width=22).grid(row=row, column=col, sticky="e", padx=6, pady=4)

    def _master_entry(self, row, col, label, variable, state="normal"):
        ttk.Label(self.master_form, text=label).grid(row=row, column=col, sticky="w", padx=6, pady=4)
        ttk.Entry(self.master_form, textvariable=variable, state=state, width=26).grid(row=row, column=col, sticky="e", padx=6, pady=4)

    def load_library_ui(self):
        if hasattr(self, "lib_concerns"):
            self._write_lines(self.lib_concerns, self.library["concerns"])
            self._write_lines(self.lib_services, self.library["services"])
            self._write_lines(self.lib_report_types, self.library["report_types"])
            self._write_lines(self.lib_categories, self.library["categories"])
            self._write_lines(self.lib_samples, self.library["samples"])
            self.refresh_template_list()
            self.refresh_formula_list()
            if hasattr(self, "problem_template_box"):
                self.problem_template_box["values"] = sorted(self.library["problem_templates"].keys())
            if hasattr(self, "formula_box"):
                self.formula_box["values"] = sorted(self.library["formulas"].keys())

    def _write_lines(self, widget, items):
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(items))

    def _read_lines(self, widget):
        return [x.strip() for x in widget.get("1.0", "end").splitlines() if x.strip()]

    def save_library_lists(self):
        self.library["concerns"] = self._read_lines(self.lib_concerns)
        self.library["services"] = self._read_lines(self.lib_services)
        self.library["report_types"] = self._read_lines(self.lib_report_types)
        self.library["categories"] = self._read_lines(self.lib_categories)
        self.library["samples"] = self._read_lines(self.lib_samples)
        save_json(self.paths["library"], self.library)
        self.reset_tabs()
        self.new_front_case()
        self.refresh_case_list()
        messagebox.showinfo("Library", "Lists saved and UI refreshed.")

    def refresh_template_list(self):
        self.tpl_list.delete(0, "end")
        for name in sorted(self.library["problem_templates"]):
            self.tpl_list.insert("end", name)

    def load_problem_template(self):
        sel = self.tpl_list.curselection()
        if not sel:
            return
        name = self.tpl_list.get(sel[0])
        self.tpl_name.set(name)
        self.tpl_text.delete("1.0", "end")
        self.tpl_text.insert("1.0", self.library["problem_templates"].get(name, ""))

    def save_problem_template(self):
        name = self.tpl_name.get().strip()
        if not name:
            messagebox.showwarning("Template", "Enter template name.")
            return
        self.library["problem_templates"][name] = self.tpl_text.get("1.0", "end").strip()
        save_json(self.paths["library"], self.library)
        self.load_library_ui()

    def delete_problem_template(self):
        name = self.tpl_name.get().strip()
        if name in self.library["problem_templates"]:
            del self.library["problem_templates"][name]
            save_json(self.paths["library"], self.library)
            self.tpl_name.set("")
            self.tpl_text.delete("1.0", "end")
            self.load_library_ui()

    def refresh_formula_list(self):
        self.formula_list.delete(0, "end")
        for name in sorted(self.library["formulas"]):
            self.formula_list.insert("end", name)

    def load_formula(self):
        sel = self.formula_list.curselection()
        if not sel:
            return
        name = self.formula_list.get(sel[0])
        obj = self.library["formulas"].get(name, {})
        self.form_name.set(name)
        self.form_expr.set(obj.get("expression", ""))
        self.form_notes.delete("1.0", "end")
        self.form_notes.insert("1.0", obj.get("notes", ""))

    def save_formula(self):
        name = self.form_name.get().strip()
        if not name:
            messagebox.showwarning("Formula", "Enter formula name.")
            return
        self.library["formulas"][name] = {
            "expression": self.form_expr.get().strip(),
            "notes": self.form_notes.get("1.0", "end").strip(),
        }
        save_json(self.paths["library"], self.library)
        self.load_library_ui()

    def delete_formula(self):
        name = self.form_name.get().strip()
        if name in self.library["formulas"]:
            del self.library["formulas"][name]
            save_json(self.paths["library"], self.library)
            self.form_name.set("")
            self.form_expr.set("")
            self.form_notes.delete("1.0", "end")
            self.load_library_ui()

    def new_front_case(self):
        t = now()
        for var in self.fd.values():
            var.set("")
        self.fd["case_id"].set(f"AH-{t.strftime('%Y%m%d-%H%M%S')}")
        self.fd["reg_date"].set(t.strftime("%Y-%m-%d"))
        self.fd["reg_time"].set(t.strftime("%H:%M"))
        self.fd["mode"].set("Walk-in")
        self.fd["preferred_language"].set("Hindi")
        self.fd["preferred_comm"].set("Call")
        self.concern_text.delete("1.0", "end")
        for v in self.service_vars.values():
            v.set(False)
        for v in self.material_vars.values():
            v.set(False)
        self.clear_photo_files()
        for block in self.crop_blocks:
            block.destroy()
        self.crop_blocks = []
        self.add_crop()
        self.nb.select(self.front_tab)

    def add_crop(self, data=None):
        block = CropBlock(self.crops_frame, self, remove_callback=lambda idx=len(self.crop_blocks): self.remove_crop(idx))
        block.pack(fill="x", expand=True, padx=2, pady=4)
        if data:
            block.set_data(data)
        self.crop_blocks.append(block)
        self.refresh_crop_titles()

    def remove_crop(self, idx):
        if 0 <= idx < len(self.crop_blocks):
            self.crop_blocks[idx].destroy()
            self.crop_blocks.pop(idx)
            self.refresh_crop_titles()

    def refresh_crop_titles(self):
        for i, block in enumerate(self.crop_blocks, start=1):
            block.config(text=f"Crop {i}")
            for child in block.winfo_children():
                if isinstance(child, ttk.Button) and child.cget("text") == "Remove Crop":
                    child.configure(command=lambda idx=i - 1: self.remove_crop(idx))

    def add_photo_files(self):
        files = filedialog.askopenfilenames(title="Select photo files", filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")])
        if files:
            self.front_photo_paths.extend(files)
            self.front_photo_paths = list(dict.fromkeys(self.front_photo_paths))
            self.update_photo_label()

    def clear_photo_files(self):
        self.front_photo_paths = []
        self.update_photo_label()

    def update_photo_label(self):
        text = f"{len(self.front_photo_paths)} file(s) selected" if self.front_photo_paths else "No files selected"
        self.photo_label.config(text=text)

    def build_front_payload(self):
        crops = []
        for block in self.crop_blocks:
            item = block.get_data()
            if item["crop_name"] or item["symptoms"] or item["concern"]:
                crops.append(item)
        return {
            "case_id": self.fd["case_id"].get().strip(),
            "registration_date": self.fd["reg_date"].get().strip(),
            "registration_time": self.fd["reg_time"].get().strip(),
            "mode_of_enquiry": self.fd["mode"].get().strip(),
            "registered_by": self.fd["registered_by"].get().strip(),
            "farmer": {
                "name": self.fd["farmer_name"].get().strip(),
                "mobile": self.fd["mobile"].get().strip(),
                "alternate_mobile": self.fd["alt_mobile"].get().strip(),
                "whatsapp": self.fd["whatsapp"].get().strip(),
                "email": self.fd["email"].get().strip(),
                "village": self.fd["village"].get().strip(),
                "post_office": self.fd["post_office"].get().strip(),
                "panchayat": self.fd["panchayat"].get().strip(),
                "tehsil": self.fd["tehsil"].get().strip(),
                "district": self.fd["district"].get().strip(),
                "state": self.fd["state"].get().strip(),
                "pin_code": self.fd["pin_code"].get().strip(),
                "preferred_language": self.fd["preferred_language"].get().strip(),
                "preferred_communication": self.fd["preferred_comm"].get().strip(),
            },
            "chief_concern": self.fd["chief_concern"].get().strip(),
            "concern_text": self.concern_text.get("1.0", "end").strip(),
            "services": [k for k, v in self.service_vars.items() if v.get()],
            "materials": [k for k, v in self.material_vars.items() if v.get()],
            "requested_visit": {
                "date": self.fd["visit_date"].get().strip(),
                "time": self.fd["visit_time"].get().strip(),
                "landmark": self.fd["landmark"].get().strip(),
            },
            "crops": crops,
        }

    def get_or_create_customer_id(self, name, phone):
        phone_key = re.sub(r"\D+", "", phone)
        by_phone = self.customer_index["by_phone"]
        if phone_key and phone_key in by_phone:
            return by_phone[phone_key]
        nxt = int(self.customer_index.get("next_customer_no", 1))
        customer_id = f"CUST-{nxt:04d}_{slug(name)}_{slug(phone_key or 'no_phone')}"
        if phone_key:
            by_phone[phone_key] = customer_id
        self.customer_index["next_customer_no"] = nxt + 1
        save_json(self.paths["customer_index"], self.customer_index)
        return customer_id

    def next_visit_no(self, date_text):
        by_date = self.counters["visits_by_date"]
        by_date[date_text] = int(by_date.get(date_text, 0)) + 1
        save_json(self.paths["counters"], self.counters)
        return by_date[date_text]

    def save_front_case(self):
        data = self.build_front_payload()
        if not data["farmer"]["name"] or not data["farmer"]["mobile"]:
            messagebox.showwarning("Required", "Farmer name and mobile are required.")
            return
        if not data["crops"]:
            messagebox.showwarning("Required", "Please add at least one crop.")
            return
        date_text = data["registration_date"] or now().strftime("%Y-%m-%d")
        visit_no = self.next_visit_no(date_text)
        customer_id = self.get_or_create_customer_id(data["farmer"]["name"], data["farmer"]["mobile"])
        crop_tag = "+".join(slug(x["crop_name"]) for x in data["crops"][:2]) or "Mixed"
        visit_id = f"{date_text}_{visit_no:03d}"
        customer_folder = self.paths["customers"] / customer_id
        visit_folder = customer_folder / "visits" / f"{visit_id}__{crop_tag}"
        attach_folder = visit_folder / "attachments"
        visit_folder.mkdir(parents=True, exist_ok=True)
        attach_folder.mkdir(parents=True, exist_ok=True)

        copied = []
        for src in self.front_photo_paths:
            srcp = Path(src)
            if srcp.exists():
                target = attach_folder / srcp.name
                try:
                    shutil.copy2(srcp, target)
                    copied.append(target.name)
                except Exception:
                    pass

        visit_data = {
            "meta": {
                "customer_id": customer_id,
                "visit_id": visit_id,
                "visit_folder": str(visit_folder),
                "status": "unseen",
                "classification": data["services"][0] if data["services"] else "Consultation",
                "created_at": now().isoformat(timespec="seconds"),
                "updated_at": now().isoformat(timespec="seconds"),
            },
            "front_desk": data,
            "master": {
                "farm_name": "",
                "farm_location": "",
                "farm_area": "",
                "production_system": "",
                "farming_system": "",
                "history_when": "",
                "pattern": "",
                "history_text": "",
                "soil_type": "",
                "drainage": "",
                "irrigation": "",
                "category": "",
                "consultant": "",
                "report_types": [],
                "samples": [],
                "recommendation_text": "",
                "next_action": "",
                "consultant_remarks": "",
            },
            "attachments": copied,
            "generated_reports": [],
        }
        save_json(visit_folder / "visit.json", visit_data)

        daily = self.paths["daily_register"] / date_text
        daily.mkdir(parents=True, exist_ok=True)
        save_json(daily / f"{visit_no:03d}__{slug(data['farmer']['name'])}.json", {
            "customer_id": customer_id,
            "visit_folder": str(visit_folder),
            "status": "unseen",
            "name": data["farmer"]["name"],
            "phone": data["farmer"]["mobile"],
            "classification": visit_data["meta"]["classification"],
            "crop_tag": crop_tag,
        })

        self.refresh_case_list()
        messagebox.showinfo("Saved", "Intake saved. A new blank case will open now.")
        self.new_front_case()

    def iter_visit_files(self):
        yield from sorted(self.paths["customers"].glob("*/visits/*/visit.json"), reverse=True)

    def refresh_case_list(self):
        if not hasattr(self, "case_tree"):
            return
        for iid in self.case_tree.get_children():
            self.case_tree.delete(iid)
        for visit_file in self.iter_visit_files():
            data = load_json(visit_file, {})
            meta = data.get("meta", {})
            front = data.get("front_desk", {})
            farmer = front.get("farmer", {})
            status = meta.get("status", "unseen")
            self.case_tree.insert("", "end", iid=str(visit_file), values=(status, farmer.get("name", ""), farmer.get("mobile", ""), front.get("registration_date", "")), tags=(status,))

    def open_selected_case(self):
        sel = self.case_tree.selection()
        if not sel:
            return
        visit_file = Path(sel[0])
        data = load_json(visit_file, {})
        self.selected_visit_file = visit_file
        if data.get("meta", {}).get("status") == "unseen":
            data["meta"]["status"] = "seen"
            data["meta"]["updated_at"] = now().isoformat(timespec="seconds")
            save_json(visit_file, data)
        self._load_master_form(data)
        self.refresh_case_list()
        self.nb.select(self.master_tab)

    def _load_master_form(self, data):
        front = data.get("front_desk", {})
        farmer = front.get("farmer", {})
        master = data.get("master", {})
        meta = data.get("meta", {})
        self.mv["farmer_name"].set(farmer.get("name", ""))
        self.mv["mobile"].set(farmer.get("mobile", ""))
        self.mv["status"].set(meta.get("status", ""))
        self.mv["classification"].set(meta.get("classification", ""))
        for key in ["consultant", "farm_name", "farm_location", "farm_area", "production_system", "farming_system", "history_when", "pattern", "soil_type", "drainage", "irrigation", "category", "next_action"]:
            self.mv[key].set(master.get(key, ""))
        self.history_text.delete("1.0", "end")
        self.history_text.insert("1.0", master.get("history_text", ""))
        self.recommend_text.delete("1.0", "end")
        self.recommend_text.insert("1.0", master.get("recommendation_text", ""))
        self.consult_text.delete("1.0", "end")
        self.consult_text.insert("1.0", master.get("consultant_remarks", ""))
        for k, v in self.report_vars.items():
            v.set(k in master.get("report_types", []))
        for k, v in self.sample_vars.items():
            v.set(k in master.get("samples", []))

    def open_selected_visit_folder(self):
        sel = self.case_tree.selection()
        if not sel:
            return
        self.open_folder(Path(sel[0]).parent)

    def open_folder(self, path: Path):
        try:
            os.startfile(str(path))
        except Exception:
            messagebox.showinfo("Folder", f"Open this folder manually:\n{path}")

    def insert_problem_template(self):
        name = self.mv["problem_template"].get().strip()
        if not name:
            return
        txt = self.library["problem_templates"].get(name, "")
        if not txt:
            return
        existing = self.recommend_text.get("1.0", "end").strip()
        merged = (existing + "\n\n" + txt).strip() if existing else txt
        self.recommend_text.delete("1.0", "end")
        self.recommend_text.insert("1.0", merged)

    def update_formula_preview(self):
        name = self.mv["formula_name"].get().strip()
        obj = self.library["formulas"].get(name, {})
        if obj:
            self.formula_preview.config(text=f"Expression: {obj.get('expression','')} | Notes: {obj.get('notes','')}")
        else:
            self.formula_preview.config(text="Formula preview will appear here.")

    def save_master_case(self, approve=False):
        if not self.selected_visit_file or not self.selected_visit_file.exists():
            messagebox.showwarning("Master", "Open a case first.")
            return
        data = load_json(self.selected_visit_file, {})
        master = data.setdefault("master", {})
        for key in ["consultant", "farm_name", "farm_location", "farm_area", "production_system", "farming_system", "history_when", "pattern", "soil_type", "drainage", "irrigation", "category", "next_action"]:
            master[key] = self.mv[key].get().strip()
        data["meta"]["classification"] = self.mv["classification"].get().strip()
        master["history_text"] = self.history_text.get("1.0", "end").strip()
        master["recommendation_text"] = self.recommend_text.get("1.0", "end").strip()
        master["consultant_remarks"] = self.consult_text.get("1.0", "end").strip()
        master["report_types"] = [k for k, v in self.report_vars.items() if v.get()]
        master["samples"] = [k for k, v in self.sample_vars.items() if v.get()]
        data["meta"]["status"] = "approved" if approve else "seen"
        data["meta"]["updated_at"] = now().isoformat(timespec="seconds")
        save_json(self.selected_visit_file, data)
        self.mv["status"].set(data["meta"]["status"])
        self.refresh_case_list()
        messagebox.showinfo("Master", "Case saved.")

    def generate_mock_report(self):
        if not self.selected_visit_file or not self.selected_visit_file.exists():
            messagebox.showwarning("Report", "Open a case first.")
            return
        self.save_master_case(approve=False)
        data = load_json(self.selected_visit_file, {})
        visit_folder = self.selected_visit_file.parent
        reports_folder = visit_folder / "mock_reports"
        reports_folder.mkdir(parents=True, exist_ok=True)

        front = data.get("front_desk", {})
        farmer = front.get("farmer", {})
        master = data.get("master", {})
        meta = data.get("meta", {})
        report_types = master.get("report_types") or [meta.get("classification", "Consultation Note")]
        created = []

        for idx, report_type in enumerate(report_types, start=1):
            base = f"{idx:02d}_{slug(report_type)}"
            txt_path = reports_folder / f"{base}.txt"
            html_path = reports_folder / f"{base}.html"
            crops = front.get("crops", [])
            crops_txt = []
            crops_html = []
            for i, crop in enumerate(crops, start=1):
                crops_txt.append(
                    f"Crop {i}: {crop.get('crop_name','')} | Variety: {crop.get('variety','')} | Stage: {crop.get('stage','')}\n"
                    f"Concern: {crop.get('concern','')}\nSymptoms: {crop.get('symptoms','')}"
                )
                crops_html.append(
                    f"<div class='card'><h3>Crop {i}: {escape(crop.get('crop_name',''))}</h3>"
                    f"<p><b>Variety:</b> {escape(crop.get('variety',''))} &nbsp; <b>Stage:</b> {escape(crop.get('stage',''))}</p>"
                    f"<p><b>Concern:</b> {escape(crop.get('concern',''))}</p>"
                    f"<p><b>Symptoms:</b> {escape(crop.get('symptoms',''))}</p></div>"
                )
            txt = f"""MOCK REPORT\nReport Type: {report_type}\nCase ID: {front.get('case_id','')}\nVisit ID: {meta.get('visit_id','')}\nStatus: {meta.get('status','')}\n\nFarmer: {farmer.get('name','')}\nMobile: {farmer.get('mobile','')}\nVillage: {farmer.get('village','')}\nTehsil: {farmer.get('tehsil','')}\nDistrict: {farmer.get('district','')}\nState: {farmer.get('state','')}\nPreferred Language: {farmer.get('preferred_language','')}\n\nChief Concern: {front.get('chief_concern','')}\nConcern Text: {front.get('concern_text','')}\nServices: {', '.join(front.get('services', []))}\nMaterials: {', '.join(front.get('materials', []))}\n\nCROPS\n{'\n\n'.join(crops_txt)}\n\nMASTER / CONSULTANT\nClassification: {meta.get('classification','')}\nCategory: {master.get('category','')}\nConsultant: {master.get('consultant','')}\nSamples: {', '.join(master.get('samples', []))}\nNext Action: {master.get('next_action','')}\n\nHistory:\n{master.get('history_text','')}\n\nRecommendation / Procedure:\n{master.get('recommendation_text','')}\n\nConsultant Remarks:\n{master.get('consultant_remarks','')}\n\nAttachments: {', '.join(data.get('attachments', []))}\n"""
            html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{escape(report_type)} Mock Report</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#222;background:#fafafa;}}
.page{{background:#fff;border:1px solid #ddd;padding:24px;max-width:980px;margin:auto;}}
h1,h2{{margin:0 0 10px 0;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;}}
.card{{border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0;background:#fcfcfc;}}
.small{{color:#555;font-size:13px;}}
pre{{white-space:pre-wrap;font-family:inherit;background:#f5f5f5;padding:12px;border-radius:8px;border:1px solid #e0e0e0;}}
</style></head><body><div class='page'>
<h1>Mock Report</h1>
<p class='small'><b>Report Type:</b> {escape(report_type)} | <b>Case ID:</b> {escape(front.get('case_id',''))} | <b>Visit ID:</b> {escape(meta.get('visit_id',''))} | <b>Status:</b> {escape(meta.get('status',''))}</p>
<h2>Farmer Details</h2>
<div class='grid'>
<div class='card'><b>Name:</b> {escape(farmer.get('name',''))}<br><b>Mobile:</b> {escape(farmer.get('mobile',''))}<br><b>Village:</b> {escape(farmer.get('village',''))}</div>
<div class='card'><b>Tehsil:</b> {escape(farmer.get('tehsil',''))}<br><b>District:</b> {escape(farmer.get('district',''))}<br><b>State:</b> {escape(farmer.get('state',''))}</div>
</div>
<h2>Chief Concern</h2>
<div class='card'><b>Primary:</b> {escape(front.get('chief_concern',''))}<br><b>Details:</b> {escape(front.get('concern_text',''))}</div>
<h2>Crops</h2>
{''.join(crops_html)}
<h2>Master / Consultant</h2>
<div class='card'><b>Classification:</b> {escape(meta.get('classification',''))}<br><b>Category:</b> {escape(master.get('category',''))}<br><b>Consultant:</b> {escape(master.get('consultant',''))}<br><b>Samples:</b> {escape(', '.join(master.get('samples', [])))}<br><b>Next Action:</b> {escape(master.get('next_action',''))}</div>
<h2>History</h2><pre>{escape(master.get('history_text',''))}</pre>
<h2>Recommendation / Procedure</h2><pre>{escape(master.get('recommendation_text',''))}</pre>
<h2>Consultant Remarks</h2><pre>{escape(master.get('consultant_remarks',''))}</pre>
<p class='small'><b>Attachments:</b> {escape(', '.join(data.get('attachments', [])))}</p>
</div></body></html>"""
            txt_path.write_text(txt, encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            created.extend([str(txt_path), str(html_path)])

        data["generated_reports"] = created
        save_json(self.selected_visit_file, data)
        messagebox.showinfo("Mock Report", f"Generated {len(created)} mock report file(s) in:\n{reports_folder}")
        self.open_folder(reports_folder)


if __name__ == "__main__":
    app = App()
    app.mainloop()
