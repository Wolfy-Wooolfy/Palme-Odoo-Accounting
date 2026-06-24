@echo off
echo ================================
echo  Palme Finance - Start All
echo ================================
echo.

cd /d D:\S\Halo\Tech\Palme-Odoo-Accounting\odoo-financial-reports

echo [1/3] Installing Python dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)
echo Done.
echo.

echo [2/3] Starting Backend (port 8200)...
start "Palme Backend" cmd /k "cd /d D:\S\Halo\Tech\Palme-Odoo-Accounting\odoo-financial-reports && venv\Scripts\activate.bat && set "PYTHONUTF8=1" && python -m uvicorn api.main:app --port 8200"

echo Waiting 10 seconds for backend to start...
timeout /t 10 /nobreak >nul

echo [3/3] Starting Frontend (port 5173)...
start "Palme Frontend" cmd /k "cd /d D:\S\Halo\Tech\Palme-Odoo-Accounting\odoo-financial-reports\dashboard && npm run dev"

timeout /t 5 /nobreak >nul

echo.
echo ================================
echo  Both servers running!
echo  Backend:  http://127.0.0.1:8200
echo  Frontend: http://localhost:5173
echo  API Docs: http://127.0.0.1:8200/docs
echo ================================
echo.
echo IMPORTANT: Keep both terminal windows OPEN
echo Close them only when you want to stop the servers.
echo.
echo Press any key to open the dashboard in browser...
pause >nul
start http://localhost:5173