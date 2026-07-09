from pathlib import Path
import runpy
import traceback
from datetime import datetime

base = Path(__file__).resolve().parent
log_file = base / 'agri_case_startup_error.txt'

try:
    runpy.run_path(str(base / 'agri_case_prototype_v2.py'), run_name='__main__')
except Exception:
    error_text = f"Time: {datetime.now().isoformat(timespec='seconds')}\n\n" + traceback.format_exc()
    log_file.write_text(error_text, encoding='utf-8')
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            'Agri Case Prototype Error',
            'The app could not start.\n\nA file named agri_case_startup_error.txt was created in the same folder.\nOpen that file and send me its contents.'
        )
        root.destroy()
    except Exception:
        print('The app could not start.')
        print('Open agri_case_startup_error.txt in the same folder and send its contents.')
        input('Press Enter to close...')
