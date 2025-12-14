# How to Upload Code to GitHub

Since Git is not currently recognized in your terminal, you will need to ensure Git is installed and then run the following commands.

## 1. Install Git
If you haven't installed it, download it from [git-scm.com](https://git-scm.com/downloads).
After installing, you might need to restart your computer or terminal.

## 2. Open Terminal
Open your terminal (PowerShell or Git Bash) in the project folder:
`D:\Freelance\expenses_tracker`

## 3. Operations

Run these commands one by one:

```bash
# 1. Initialize Git
git init

# 2. Add all files (respecting .gitignore)
git add .

# 3. Commit the changes
git commit -m "Initial commit of Expense Tracker"

# 4. Link to your GitHub Repository
git remote add origin https://github.com/padhariabhavesh/expenses_tracker.git
# Note: If it says "remote origin already exists", use this instead:
# git remote set-url origin https://github.com/padhariabhavesh/expenses_tracker.git

# 5. Rename branch to main
git branch -M main

# 6. Push to GitHub
git push -u origin main
```

## Troubleshooting
-   **Authentication**: You may be asked to sign in. Follow the browser prompts.
-   **Errors**: If `git push` fails because of "refused", you might need to pull first: `git pull origin main --rebase` (only if the repo wasn't empty).
