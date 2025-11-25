import os
import hashlib
import re
import zipfile
import shutil

# --- CONFIGURAÇÃO ---
# Diretório base onde os addons (pastas) estão localizados (raiz do seu repositório)
ADDONS_DIR = '.' 
# Nome da pasta do seu repositório (onde os manifestos e ZIPs serão salvos)
OUTPUT_REPO_DIR = 'repository.anmstream' 
# Pastas a serem ignoradas durante a busca por addons
EXCLUDE_DIRS = ['repository.anmstream', '.git', '.github', '__pycache__']
# Nova pasta para guardar versões antigas
OLD_VERSIONS_DIR = os.path.join(OUTPUT_REPO_DIR, 'old_versions')

def generate_addons_xml():
    """
    Busca por todos os addons (pastas com addon.xml) e cria o arquivo mestre addons.xml 
    e seu hash MD5 na pasta do repositório.
    """
    print("Iniciando geração de manifestos (addons.xml e MD5)...")
    addons_xml_content = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    
    # 1. Busca e processa os addons
    for root, dirs, files in os.walk(ADDONS_DIR):
        # Filtra pastas a serem ignoradas
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        
        if 'addon.xml' in files:
            addon_path = os.path.join(root, 'addon.xml')
            try:
                with open(addon_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                    
                # Extrai o bloco <addon> inteiro
                addon_block_match = re.search(r'(<addon\s+id="[^"]+".*?</addon>)', xml_content, re.DOTALL)
                if addon_block_match:
                    addon_block = addon_block_match.group(1).strip()
                    addons_xml_content += f"\n{addon_block}\n"
                    print(f"  - XML encontrado e processado: {os.path.basename(root)}")
                
            except Exception as e:
                print(f"Erro ao processar {addon_path}: {e}")

    addons_xml_content += '</addons>\n'
    
    # 2. Salva addons.xml na pasta do repositório
    addons_xml_path = os.path.join(OUTPUT_REPO_DIR, 'addons.xml')
    with open(addons_xml_path, 'w', encoding='utf-8') as f:
        f.write(addons_xml_content)
    print(f"-> Manifestos salvos em: {addons_xml_path}")
    
    # 3. Gera o MD5
    md5_hash = hashlib.md5(addons_xml_content.encode('utf-8')).hexdigest()
    md5_path = os.path.join(OUTPUT_REPO_DIR, 'addons.xml.md5')
    with open(md5_path, 'w') as f:
        f.write(md5_hash)
    print(f"-> Hash MD5 salvo em: {md5_path}")
    
def create_addon_zips():
    """
    Cria arquivos ZIP de cada addon, move o ZIP antigo e salva o novo na pasta do repositório.
    """
    print("\nIniciando criação dos arquivos ZIP dos addons...")
    
    # Cria a pasta old_versions se ela não existir
    if not os.path.exists(OLD_VERSIONS_DIR):
        os.makedirs(OLD_VERSIONS_DIR)
        print(f"  - Criada pasta de histórico: {OLD_VERSIONS_DIR}")
    
    for root, dirs, files in os.walk(ADDONS_DIR):
        # Filtra pastas a serem ignoradas
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
        
        if 'addon.xml' in files:
            addon_id = os.path.basename(root)
            addon_xml_path = os.path.join(root, 'addon.xml')
            
            # Só criamos ZIPs para addons, não para a pasta de repositório em si.
            if addon_id == OUTPUT_REPO_DIR:
                continue

            try:
                # 1. Ler a versão (USANDO A REGEX CORRIGIDA)
                with open(addon_xml_path, 'r', encoding='utf-8') as f:
                    xml_content = f.read()
                
                # A nova Regex busca a versão APENAS na tag <addon, ignorando a declaração <?xml
                version_match = re.search(r'<addon.*?version="([^"]+)"', xml_content, re.DOTALL)
                
                if version_match:
                    version = version_match.group(1)
                    zip_filename = f"{addon_id}-{version}.zip"
                    zip_path = os.path.join(OUTPUT_REPO_DIR, zip_filename)

                    print(f"  - Criando ZIP: {zip_filename} (Versão {version})...")
                    
                    # --- NOVA LÓGICA DE MOVER ZIP ANTIGO ---
                    for filename in os.listdir(OUTPUT_REPO_DIR):
                        if filename.startswith(f"{addon_id}-") and filename.endswith(".zip"):
                            old_version_zip = os.path.join(OUTPUT_REPO_DIR, filename)
                            
                            # Move se o arquivo encontrado for DIFERENTE do que vamos criar
                            if old_version_zip != zip_path:
                                old_zip_name = os.path.basename(old_version_zip)
                                destination_path = os.path.join(OLD_VERSIONS_DIR, old_zip_name)
                                
                                # Move (substituindo se já existir)
                                shutil.move(old_version_zip, destination_path)
                                print(f"    [Movido Antigo] {old_zip_name} -> old_versions")
                                break # Deve haver apenas um ZIP antigo por addon

                    # 2. Cria o NOVO ZIP
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                        for foldername, subfolders, filenames in os.walk(root):
                            subfolders[:] = [sf for sf in subfolders if sf not in EXCLUDE_DIRS and not sf.startswith('.')]
                            for filename in filenames:
                                if not filename.endswith(('.pyc', '.git')) and filename not in ['.DS_Store', 'repo_generator.py']:
                                    file_path = os.path.join(foldername, filename)
                                    arcname = os.path.join(addon_id, os.path.relpath(file_path, root))
                                    zf.write(file_path, arcname)
                    print(f"  - Sucesso. NOVO ZIP salvo em: {zip_path}")
                
            except Exception as e:
                print(f"Erro ao criar ZIP para {addon_id}: {e}")

if __name__ == '__main__':
    # Garante que a pasta do repositório exista
    if not os.path.exists(OUTPUT_REPO_DIR):
        print(f"Criando pasta: {OUTPUT_REPO_DIR}")
        os.makedirs(OUTPUT_REPO_DIR)
        
    generate_addons_xml()
    create_addon_zips()
    
    print("\n========================================================")
    print("  Processo de Geração de Repositório Concluído!")
    print("  1. Verifique se a pasta 'repository.anmstream' contém:")
    print("     - addons.xml")
    print("     - addons.xml.md5")
    print("     - plugin.video.anmstream-X.X.X.zip (o novo!)")
    print("  2. Os ZIPs antigos foram movidos para a pasta 'old_versions'.")
    print("  3. Faça o COMMIT e PUSH de TODAS as alterações para o GitHub.")
    print("========================================================")