@echo off
:: --- CONFIGURAÇÃO ---

:: Muda o diretório de execução para a pasta onde este arquivo está salvo
cd /d "%~dp0"

:: Aguarda 30 segundos para garantir que a internet conectou após o boot
echo Aguardando conexao de rede...
timeout /t 30 /nobreak >nul

:: --- INSTALAÇÃO ---
echo Verificando dependencias...
pip install requests beautifulsoup4

:: --- EXECUÇÃO ---
echo Iniciando o Bot de Animes...
:: Substitua pelo nome exato do seu arquivo python se for diferente
python animes_full_manager_refatorado.py

:: Se o script fechar por erro, pausa para ver a mensagem (apenas se rodar visível)
pause