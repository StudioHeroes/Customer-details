import json
import os
import sys
import time
import uuid
import tempfile
import subprocess
from contextlib import contextmanager
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

APP_TITLE = "Customer Case Register"
LOCK_FILE = ".records.lock"
DEFAULT_PROBLEMS = [
    "Nematode",
    "Fungus",
    "Wilt",
    "Leaf spot",
    "Yellowing",
    "Root rot",
]
DEFAULT_SOLUTIONS = [
    "Inspect roots",
    "Apply recommended treatment",
    "Improve drainage",
    "Follow up after 7 days",
    "Isolate affected item",
]


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class DataStore:
    def __init__(self, folder: str):
        self.set_folder(folder)

    def set_folder(self, folder: str):
        self.folder = os.path.abspath(folder)
        os.makedirs(self.folder, exist_ok=True)
        self.records_path = os.path.join(self.folder, "records.json")
        self.problems_path = os.path.join(self.folder, "problems.json")
        self.solutions_path = os.path.join(self.folder, "solutions.json")
        self.lock_path = os.path.join(self.folder, LOCK_FILE)
        self._ensure_files()

    def _ensure_files(self):
        if not os.path.exists(self.records_path):
            self._write_json(self.records_path, {"records": []})
        if not os.path.exists(self.problems_path):
            self._write_json(self.problems_path, {"items": DEFAULT_PROBLEMS})
        if not os.path.exists(self.solutions_path):
            self._write_json(self.solutions_path, {"items": DEFAULT_SOLUTIONS})

    def _read_json(self, path: str, fallback):
        if not os.path.exists(path):
            return fallback
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return fallback

    def _write_json(self, path: str, data):
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)

    @contextmanager
    def acquire_lock(self, timeout=8):
        start = time.time()
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.close(fd)
                break
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(self.lock_path)
                    if age > 30:
                        os.remove(self.lock_path)
                        continue
                except OSError:
                    pass
                if time.time() - start > timeout:
                    raise TimeoutError("Another PC is saving right now. Please wait a few seconds and try again.")
                time.sleep(0.2)
        try:
            yield
        finally:
            try:
                os.remove(self.lock_path)
            except OSError:
                pass

    def load_records(self):
        data = self._read_json(self.records_path, {"records": []})
        return data.get("records", [])

    def save_records(self, records):
        with self.acquire_lock():
            self._write_json(self.records_path, {"records": records})

    def load_items(self, kind: str):
        path = self.problems_path if kind == "problems" else self.solutions_path
        data = self._read_json(path, {"items": []})
        items = [normalize_text(x) for x in data.get("items", []) if normalize_text(str(x))]
        seen = set()
        clean = []
        for item in items:
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                clean.append(item)
        clean.sort(key=str.casefold)
        return clean

    def save_items(self, kind: str, items):
        path = self.problems_path if kind == "problems" else self.solutions_path
        cleaned = []
        seen = set()
        for item in items:
            text = normalize_text(item)
            if not text:
                continue
            key = text.casefold()
            if key not in seen:
                seen.add(key)
                cleaned.append(text)
        cleaned.sort(key=str.casefold)
        with self.acquire_lock():
            self._write_json(path, {"items": cleaned})
        return cleaned


class MultiSelectEditor(ttk.LabelFrame):
    def __init__(self, master, title, kind, options_getter, options_saver):
        super().__init__(master, text=title, padding=8)
        self.kind = kind
        self.options_getter = options_getter
        self.options_saver = options_saver
        self.options = self.options_getter(self.kind)
        self.selected = []
        self.query_var = tk.StringVar()
        self._build()
        self.refresh_suggestions()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Type to filter or add:").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.query_var)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
        entry.bind("<KeyRelease>", lambda e: self.refresh_suggestions())
        entry.bind("<Return>", lambda e: self.add_typed())
        ttk.Button(top, text="Add typed", command=self.add_typed).pack(side="left")

        middle = ttk.Frame(self)
        middle.pack(fill="both", expand=True)
        left = ttk.Frame(middle)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Matches").pack(anchor="w")
        self.suggestion_list = tk.Listbox(left, height=6, exportselection=False)
        self.suggestion_list.pack(fill="both", expand=True)
        self.suggestion_list.bind("<Double-Button-1>", lambda e: self.add_from_suggestions())

        buttons = ttk.Frame(middle)
        buttons.pack(side="left", fill="y", padx=8)
        ttk.Button(buttons, text="Add →", command=self.add_from_suggestions).pack(fill="x", pady=(18, 6))
        ttk.Button(buttons, text="← Remove", command=self.remove_selected).pack(fill="x", pady=6)
        ttk.Button(buttons, text="Manage list", command=self.manage_list).pack(fill="x", pady=6)

        right = ttk.Frame(middle)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text="Selected").pack(anchor="w")
        self.selected_list = tk.Listbox(right, height=6, exportselection=False)
        self.selected_list.pack(fill="both", expand=True)

    def refresh_options(self):
        self.options = self.options_getter(self.kind)
        self.refresh_suggestions()

    def refresh_suggestions(self):
        query = normalize_text(self.query_var.get()).casefold()
        starts = []
        contains = []
        for item in self.options:
            item_cf = item.casefold()
            if not query:
                starts.append(item)
            elif item_cf.startswith(query):
                starts.append(item)
            elif query in item_cf:
                contains.append(item)
        items = starts + contains
        self.suggestion_list.delete(0, tk.END)
        for item in items[:200]:
            self.suggestion_list.insert(tk.END, item)

    def add_item(self, item):
        text = normalize_text(item)
        if not text:
            return
        if text.casefold() not in {x.casefold() for x in self.options}:
            self.options.append(text)
            self.options = self.options_saver(self.kind, self.options)
        if text.casefold() not in {x.casefold() for x in self.selected}:
            self.selected.append(text)
            self.selected.sort(key=str.casefold)
        self.render_selected()
        self.refresh_options()
        self.query_var.set("")

    def add_typed(self):
        text = self.query_var.get()
        if not normalize_text(text):
            return
        self.add_item(text)

    def add_from_suggestions(self):
        selection = self.suggestion_list.curselection()
        if not selection:
            self.add_typed()
            return
        text = self.suggestion_list.get(selection[0])
        self.add_item(text)

    def remove_selected(self):
        selection = self.selected_list.curselection()
        if not selection:
            return
        idx = selection[0]
        del self.selected[idx]
        self.render_selected()

    def render_selected(self):
        self.selected_list.delete(0, tk.END)
        for item in self.selected:
            self.selected_list.insert(tk.END, item)

    def get_selected(self):
        return list(self.selected)

    def set_selected(self, items):
        clean = []
        seen = set()
        for item in items or []:
            text = normalize_text(str(item))
            if not text:
                continue
            key = text.casefold()
            if key not in seen:
                seen.add(key)
                clean.append(text)
                if key not in {x.casefold() for x in self.options}:
                    self.options.append(text)
        self.selected = sorted(clean, key=str.casefold)
        self.options = self.options_saver(self.kind, self.options)
        self.render_selected()
        self.refresh_options()

    def manage_list(self):
        dialog = tk.Toplevel(self)
        dialog.title(f"Manage {self.kind.title()}")
        dialog.geometry("420x420")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Items in {self.kind}. Double-click to remove.").pack(anchor="w")
        lb = tk.Listbox(frame, exportselection=False)
        lb.pack(fill="both", expand=True, pady=8)
        for item in self.options_getter(self.kind):
            lb.insert(tk.END, item)

        row = ttk.Frame(frame)
        row.pack(fill="x")
        new_var = tk.StringVar()
        ttk.Entry(row, textvariable=new_var).pack(side="left", fill="x", expand=True)

        def add_new():
            text = normalize_text(new_var.get())
            if not text:
                return
            current = [lb.get(i) for i in range(lb.size())]
            if text.casefold() not in {x.casefold() for x in current}:
                current.append(text)
                current.sort(key=str.casefold)
                lb.delete(0, tk.END)
                for item in current:
                    lb.insert(tk.END, item)
            new_var.set("")

        def remove_current(event=None):
            sel = lb.curselection()
            if not sel:
                return
            lb.delete(sel[0])

        lb.bind("<Double-Button-1>", remove_current)
        ttk.Button(row, text="Add", command=add_new).pack(side="left", padx=(6, 0))

        def save_and_close():
            items = [lb.get(i) for i in range(lb.size())]
            self.options = self.options_saver(self.kind, items)
            self.selected = [x for x in self.selected if x.casefold() in {y.casefold() for y in self.options}]
            self.render_selected()
            self.refresh_options()
            dialog.destroy()

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="Save", command=save_and_close).pack(side="right")
        ttk.Button(bottom, text="Cancel", command=dialog.destroy).pack(side="right", padx=(0, 6))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.store = DataStore(self.default_data_folder())
        self.records = []
        self.current_id = None
        self.search_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=self.store.folder)
        self._build_ui()
        self.reload_all()

    def default_data_folder(self):
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        return os.path.join(base, "shared_data")

    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 8))
        ttk.Label(top, text="Shared data folder:").pack(side="left")
        ttk.Entry(top, textvariable=self.folder_var, state="readonly").pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Change folder", command=self.change_folder).pack(side="left")
        ttk.Button(top, text="Reload", command=self.reload_all).pack(side="left", padx=(6, 0))

        paned = ttk.Panedwindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        right = ttk.Frame(paned)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        form = ttk.LabelFrame(left, text="Case form", padding=10)
        form.pack(fill="both", expand=True)

        basic = ttk.Frame(form)
        basic.pack(fill="x")
        ttk.Label(basic, text="Person name").grid(row=0, column=0, sticky="w")
        ttk.Entry(basic, textvariable=self.name_var).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(basic, text="Phone number").grid(row=0, column=1, sticky="w")
        ttk.Entry(basic, textvariable=self.phone_var).grid(row=1, column=1, sticky="ew")
        basic.columnconfigure(0, weight=1)
        basic.columnconfigure(1, weight=1)

        self.problem_editor = MultiSelectEditor(form, "Problems", "problems", self.store.load_items, self.store.save_items)
        self.problem_editor.pack(fill="both", expand=True, pady=(10, 8))

        symptom_frame = ttk.LabelFrame(form, text="Symptoms", padding=8)
        symptom_frame.pack(fill="both", expand=True, pady=(0, 8))
        self.symptom_text = tk.Text(symptom_frame, height=6, wrap="word")
        self.symptom_text.pack(fill="both", expand=True)

        self.solution_editor = MultiSelectEditor(form, "Solutions", "solutions", self.store.load_items, self.store.save_items)
        self.solution_editor.pack(fill="both", expand=True, pady=(0, 8))

        custom_frame = ttk.LabelFrame(form, text="Custom solution notes", padding=8)
        custom_frame.pack(fill="both", expand=True, pady=(0, 8))
        self.custom_solution_text = tk.Text(custom_frame, height=4, wrap="word")
        self.custom_solution_text.pack(fill="both", expand=True)

        button_row = ttk.Frame(form)
        button_row.pack(fill="x", pady=(4, 0))
        ttk.Button(button_row, text="New", command=self.clear_form).pack(side="left")
        ttk.Button(button_row, text="Save / Update", command=self.save_record).pack(side="left", padx=6)
        ttk.Button(button_row, text="Delete", command=self.delete_record).pack(side="left")
        ttk.Button(button_row, text="Print view", command=self.print_view).pack(side="right")

        list_frame = ttk.LabelFrame(right, text="Saved cases", padding=10)
        list_frame.pack(fill="both", expand=True)
        search_row = ttk.Frame(list_frame)
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Search").pack(side="left")
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=6)
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_record_list())

        columns = ("name", "phone", "problems", "updated")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=18)
        self.tree.heading("name", text="Name")
        self.tree.heading("phone", text="Phone")
        self.tree.heading("problems", text="Problems")
        self.tree.heading("updated", text="Updated")
        self.tree.column("name", width=140)
        self.tree.column("phone", width=110)
        self.tree.column("problems", width=230)
        self.tree.column("updated", width=140)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.load_selected_record())

        hint = ttk.Label(
            list_frame,
            text="Tip: put the same shared folder on every PC. The app will read records.json, problems.json and solutions.json from there.",
            wraplength=330,
            foreground="#555555",
        )
        hint.pack(anchor="w", pady=(8, 0))

    def change_folder(self):
        folder = filedialog.askdirectory(title="Choose shared data folder", initialdir=self.store.folder)
        if not folder:
            return
        try:
            self.store.set_folder(folder)
            self.folder_var.set(self.store.folder)
            self.reload_all()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not use that folder.\n\n{exc}")

    def reload_all(self):
        self.records = self.store.load_records()
        self.problem_editor.refresh_options()
        self.solution_editor.refresh_options()
        self.refresh_record_list()

    def refresh_record_list(self):
        query = self.search_var.get().strip().casefold()
        for item in self.tree.get_children():
            self.tree.delete(item)
        items = sorted(self.records, key=lambda r: r.get("updated_at", ""), reverse=True)
        for record in items:
            haystack = " | ".join([
                str(record.get("name", "")),
                str(record.get("phone", "")),
                ", ".join(record.get("problems", [])),
                record.get("symptoms", ""),
                ", ".join(record.get("solutions", [])),
                record.get("custom_solution", ""),
            ]).casefold()
            if query and query not in haystack:
                continue
            self.tree.insert(
                "",
                tk.END,
                iid=record["id"],
                values=(
                    record.get("name", ""),
                    record.get("phone", ""),
                    ", ".join(record.get("problems", []))[:60],
                    record.get("updated_at", ""),
                ),
            )

    def validate_form(self):
        name = normalize_text(self.name_var.get())
        phone = normalize_text(self.phone_var.get())
        if not name:
            messagebox.showwarning(APP_TITLE, "Please enter the person name.")
            return None
        if not phone:
            messagebox.showwarning(APP_TITLE, "Please enter the phone number.")
            return None
        record = {
            "id": self.current_id or str(uuid.uuid4()),
            "name": name,
            "phone": phone,
            "problems": self.problem_editor.get_selected(),
            "symptoms": self.symptom_text.get("1.0", "end").strip(),
            "solutions": self.solution_editor.get_selected(),
            "custom_solution": self.custom_solution_text.get("1.0", "end").strip(),
            "updated_at": now_text(),
        }
        if not self.current_id:
            record["created_at"] = record["updated_at"]
        else:
            old = next((r for r in self.records if r["id"] == self.current_id), None)
            record["created_at"] = old.get("created_at", record["updated_at"]) if old else record["updated_at"]
        return record

    def save_record(self):
        record = self.validate_form()
        if not record:
            return
        try:
            replaced = False
            new_records = []
            for item in self.records:
                if item["id"] == record["id"]:
                    new_records.append(record)
                    replaced = True
                else:
                    new_records.append(item)
            if not replaced:
                new_records.append(record)
            self.store.save_records(new_records)
            self.records = new_records
            self.current_id = record["id"]
            self.refresh_record_list()
            messagebox.showinfo(APP_TITLE, "Record saved.")
        except TimeoutError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not save the record.\n\n{exc}")

    def load_selected_record(self):
        selected = self.tree.selection()
        if not selected:
            return
        record_id = selected[0]
        record = next((r for r in self.records if r["id"] == record_id), None)
        if not record:
            return
        self.current_id = record["id"]
        self.name_var.set(record.get("name", ""))
        self.phone_var.set(record.get("phone", ""))
        self.problem_editor.set_selected(record.get("problems", []))
        self.solution_editor.set_selected(record.get("solutions", []))
        self.symptom_text.delete("1.0", tk.END)
        self.symptom_text.insert("1.0", record.get("symptoms", ""))
        self.custom_solution_text.delete("1.0", tk.END)
        self.custom_solution_text.insert("1.0", record.get("custom_solution", ""))

    def clear_form(self):
        self.current_id = None
        self.name_var.set("")
        self.phone_var.set("")
        self.problem_editor.set_selected([])
        self.solution_editor.set_selected([])
        self.symptom_text.delete("1.0", tk.END)
        self.custom_solution_text.delete("1.0", tk.END)

    def delete_record(self):
        if not self.current_id:
            messagebox.showinfo(APP_TITLE, "Open a record first, then delete it.")
            return
        if not messagebox.askyesno(APP_TITLE, "Delete this record?"):
            return
        try:
            self.records = [r for r in self.records if r["id"] != self.current_id]
            self.store.save_records(self.records)
            self.clear_form()
            self.refresh_record_list()
            messagebox.showinfo(APP_TITLE, "Record deleted.")
        except TimeoutError as exc:
            messagebox.showwarning(APP_TITLE, str(exc))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Could not delete the record.\n\n{exc}")

    def compose_print_text(self):
        record = self.validate_form()
        if not record:
            return None
        lines = [
            APP_TITLE,
            "=" * 50,
            f"Name: {record['name']}",
            f"Phone: {record['phone']}",
            f"Problems: {', '.join(record['problems']) if record['problems'] else '-'}",
            "",
            "Symptoms:",
            record["symptoms"] or "-",
            "",
            f"Solutions: {', '.join(record['solutions']) if record['solutions'] else '-'}",
            "",
            "Custom solution notes:",
            record["custom_solution"] or "-",
            "",
            f"Updated: {record['updated_at']}",
        ]
        return "\n".join(lines)

    def print_view(self):
        text = self.compose_print_text()
        if not text:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Print view")
        dialog.geometry("720x520")
        box = tk.Text(dialog, wrap="word")
        box.pack(fill="both", expand=True)
        box.insert("1.0", text)

        def save_txt():
            path = filedialog.asksaveasfilename(
                title="Save printable text",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")],
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(box.get("1.0", "end").strip() + "\n")
            messagebox.showinfo(APP_TITLE, "Printable text saved.")

        def send_print():
            content = box.get("1.0", "end").strip() + "\n"
            if sys.platform.startswith("win") and hasattr(os, "startfile"):
                temp_path = os.path.join(tempfile.gettempdir(), "customer_case_print.txt")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)
                try:
                    os.startfile(temp_path, "print")
                except OSError:
                    messagebox.showinfo(APP_TITLE, "Windows print command did not open. Use Save TXT instead.")
            else:
                save_txt()

        bar = ttk.Frame(dialog, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Save TXT", command=save_txt).pack(side="right")
        ttk.Button(bar, text="Print / export", command=send_print).pack(side="right", padx=(0, 6))


if __name__ == "__main__":
    app = App()
    app.mainloop()
