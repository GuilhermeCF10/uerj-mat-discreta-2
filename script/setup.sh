#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------
# Configurações
# ------------------------------------------------------------------
ENV_NAME="uerj-mat-discreta-2"
PY_VERSION="3.12"
OS="$(uname -s)"

# ------------------------------------------------------------------
# Funções auxiliares
# ------------------------------------------------------------------
create_conda_env() {
  if ! command -v conda >/dev/null 2>&1; then
    echo "❌ Conda não encontrado no PATH. Instale Miniconda/Anaconda."
    exit 1
  fi
  if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "✅ Ambiente "$ENV_NAME" já existe."
  else
    echo "⚙️  Criando ambiente Conda "$ENV_NAME"…"
    conda create -y -n "$ENV_NAME" "python=$PY_VERSION"
  fi
}

activate_env_and_run() {
  eval "$(conda shell.bash hook)"
  conda activate "$ENV_NAME"

  echo "⚙️  Instalando dependências Python…"
  pip install -r requirements.txt

  echo "🚀 Executando main.py…"
  python3 main.py
}

# ------------------------------------------------------------------
# Execução principal
# ------------------------------------------------------------------
create_conda_env
activate_env_and_run
