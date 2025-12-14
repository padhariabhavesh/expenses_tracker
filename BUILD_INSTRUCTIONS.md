# How to Generate the .exe File

This guide explains how to convert the Expenses Tracker web application into a standalone Windows Executable file.

## Prerequisites

1.  **Python Installed**: Ensure you have Python installed (3.10 or newer recommended).
2.  **Terminal**: Open Command Prompt (cmd) or PowerShell in this project folder (`d:\Freelance\expenses_tracker`).

## Quick Start (Using Script)

We have provided a script to automate the process.

1.  Open **PowerShell** in the project directory.
2.  Run the following command:
    ```powershell
    .\build_exe.ps1
    ```
3.  Wait for the process to complete.

## Manual Steps

If you prefer to run the commands manually:

1.  **Install Application Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install PyInstaller**:
    ```bash
    pip install pyinstaller
    ```

3.  **Build the Executable**:
    ```bash
    python -m PyInstaller Padharia.spec --clean --noconfirm
    ```

## Locate the Output

Once the build is successful, you will find a **`dist`** folder in your project directory.

-   **Executable File**: `dist\Padharia.exe`

You can move this `.exe` file to any location, but keep in mind:
-   It will generate a `expenses.db` and `debug.log` in the same folder where it runs.

## Troubleshooting

-   **Antivirus**: Sometimes Windows Defender flags new .exe files. You may need to "Allow" it.
-   **Missing Data**: The `expenses.db` is a local file. If you move the .exe to a new computer, you start with an empty database unless you also copy the `.db` file.
