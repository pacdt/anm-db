@echo off
:: --- CONFIGURAÇÃO ---

:: Muda o diretório de execução para a pasta onde este arquivo está salvo
cd /d "%~dp0"

:: Aguarda 10 segundos para garantir que a internet conectou após o boot
echo Aguardando conexao de rede...
timeout /t 10 /nobreak >nul

:: --- INSTALACAO ---
echo Verificando dependencias...
pip install aiohttp aiofiles tqdm beautifulsoup4
cls
:: --- EXECUÇÃO ---
echo Iniciando o Bot de Animes...
:: Substitua pelo nome exato do seu arquivo python se for diferente
python script.py

echo Iniciando a criacao da API...
:: Substitua pelo nome exato do seu arquivo python se for diferente
python api.py

echo Iniciando atualizacao do Repositorio...
echo Adicionando novas atualizacoes...
git add .

echo Realizando Commit...
git commit -m "Atualizacao automatica em %DATE% as %TIME% "

echo Enviando atualizacoes...
git push origin main

:: Se o script fechar por erro, pausa para ver a mensagem (apenas se rodar visível)
pause