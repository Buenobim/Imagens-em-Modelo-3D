# Instala a plataforma "Imagens em Modelo 3D" do zero (Windows + placa NVIDIA com >= 8 GB).
# Uso (PowerShell, na pasta do projeto):  .\instalar.ps1
# Precisa: Python 3.12, Git, Blender 5.0 e Bambu Studio 2.05 instalados nos caminhos padrao.
# Baixa ~18 GB (PyTorch + modelos 2.1 e 2.0). Ao baixar o modelo voce aceita a
# Tencent Hunyuan 3D 2.0 Community License (vendor/Hunyuan3D-2/LICENSE).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$HUNYUAN_COMMIT = "f8db630"     # Hunyuan3D-2 (2.0) testado
$HUNYUAN21_COMMIT = "82920d6"   # Hunyuan3D-2.1 testado

function Step($msg, $block) { Write-Host "`n== $msg"; & $block; if ($LASTEXITCODE -ne 0) { throw "FALHOU: $msg" } }

if (-not (Test-Path .venv)) { Step "Criando ambiente Python" { python -m venv .venv } }
$py = ".venv\Scripts\python.exe"
Step "Atualizando pip" { & $py -m pip install -q --upgrade pip }
Step "PyTorch com CUDA 12.4 (~2,5 GB)" { & $py -m pip install --no-cache-dir -q torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124 }
if (-not (Test-Path vendor\Hunyuan3D-2)) {
    Step "Codigo oficial do Hunyuan3D-2" { git clone -q https://github.com/Tencent-Hunyuan/Hunyuan3D-2.git vendor/Hunyuan3D-2 }
}
Step "Fixando a versao testada do Hunyuan3D-2" { git -C vendor/Hunyuan3D-2 checkout -q $HUNYUAN_COMMIT }
if (-not (Test-Path vendor\Hunyuan3D-2.1)) {
    # sem os dados de treino (nomes de arquivo longos demais para o Windows) e sem o modulo de textura
    Step "Codigo oficial do Hunyuan3D-2.1" {
        git clone -q --no-checkout https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1.git vendor/Hunyuan3D-2.1
        git -C vendor/Hunyuan3D-2.1 sparse-checkout init --no-cone
        Set-Content -Encoding ascii vendor/Hunyuan3D-2.1/.git/info/sparse-checkout "/*`n!/hy3dshape/tools/`n!/hy3dpaint/"
        git -C vendor/Hunyuan3D-2.1 checkout -q $HUNYUAN21_COMMIT
    }
}
Step "Pacote hy3dgen" { & $py -m pip install --no-cache-dir -q -e vendor/Hunyuan3D-2 }
Step "Dependencias nas versoes testadas" { & $py -m pip install --no-cache-dir -q -r requirements.txt }
cmd /c "`"$py`" -m pip uninstall -y -q hf-gradio >nul 2>&1"   # pacote extra que conflita (se existir)
Step "Conferindo dependencias" { & $py -m pip check }
Step "Modelo Hunyuan3D-2.1 (~7,4 GB, qualidade Alta/Maxima)" { & $py scripts\baixar_modelo.py v21 }
Step "Modelo Hunyuan3D-2.0 turbo (~5,3 GB, qualidade Rapida)" { & $py scripts\baixar_modelo.py turbo }
Step "Perfis oficiais da A1 mini" { & $py impressao\bambu_perfis.py }
Step "Placa de video" { & $py -c "import torch; assert torch.cuda.is_available(), 'CUDA indisponivel'; print(torch.cuda.get_device_name(0))" }
Write-Host "`nPronto. Para usar: clique duas vezes em iniciar.bat"
