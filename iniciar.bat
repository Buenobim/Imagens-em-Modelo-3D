@echo off
rem Abre a plataforma "Imagens em Modelo 3D" no navegador (http://127.0.0.1:7860)
cd /d "%~dp0"
title Imagens em Modelo 3D - nao feche esta janela enquanto estiver usando
".venv\Scripts\python.exe" app\plataforma.py
pause
