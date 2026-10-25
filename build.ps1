# Сборка WARDOGS-OCR.exe (папка dist\WARDOGS-OCR\ — её и раздавать, упаковав в zip).
# Запуск из папки проекта:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -q -r requirements.txt pyinstaller
& $py -m PyInstaller --noconfirm --clean --windowed --name WARDOGS-OCR `
    --add-data "templates;templates" `
    --add-data "data\attachments.json;data" `
    --collect-all winrt `
    --collect-all windows_capture `
    app.py
Compress-Archive -Path dist\WARDOGS-OCR\* -DestinationPath dist\WARDOGS-OCR.zip -Force
Write-Host "Готово: dist\WARDOGS-OCR\WARDOGS-OCR.exe и dist\WARDOGS-OCR.zip"
