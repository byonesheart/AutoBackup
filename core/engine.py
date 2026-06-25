"""AutoBackup v1.1.1 备份引擎"""
import os
import zipfile
from datetime import datetime

try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False


def backup_source(source_path, dest_dir, password=None):
    """将 source_path（文件或文件夹）压缩成 ZIP 文件保存到 dest_dir。
    返回 (zip_path, skipped_files)，失败返回 (None, [])。
    """
    source_path = os.path.normpath(source_path)
    
    is_file = os.path.isfile(source_path)
    is_dir = os.path.isdir(source_path)
    
    if not is_file and not is_dir:
        return None, []

    source_name = os.path.basename(source_path)
    
    if is_dir:
        backup_folder_name = f"{source_name}备份"
    else:
        backup_folder_name = f"{os.path.splitext(source_name)[0]}备份"
    
    backup_folder = os.path.join(dest_dir, backup_folder_name)
    os.makedirs(backup_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"{source_name}_{timestamp}.zip"
    zip_path = os.path.join(backup_folder, zip_name)

    skipped = []
    
    if password and HAS_PYZIPPER:
        with pyzipper.AESZipFile(zip_path, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
            zf.setpassword(password.encode('utf-8'))
            if is_file:
                try:
                    zf.write(source_path, source_name)
                except OSError:
                    skipped.append(source_path)
            else:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(source_name, os.path.relpath(file_path, source_path))
                        try:
                            zf.write(file_path, arcname)
                        except OSError:
                            skipped.append(file_path)
    else:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if is_file:
                try:
                    zf.write(source_path, source_name)
                except OSError:
                    skipped.append(source_path)
            else:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(source_name, os.path.relpath(file_path, source_path))
                        try:
                            zf.write(file_path, arcname)
                        except OSError:
                            skipped.append(file_path)

    return zip_path, skipped


def restore_backup(zip_path, dest_dir, password=None):
    """从 ZIP 文件恢复备份到 dest_dir。
    返回 (success, error_message)
    """
    if not os.path.exists(zip_path):
        return False, "备份文件不存在"

    try:
        if password and HAS_PYZIPPER:
            with pyzipper.AESZipFile(zip_path, 'r') as zf:
                zf.setpassword(password.encode('utf-8'))
                zf.extractall(dest_dir)
        elif password:
            with pyzipper.AESZipFile(zip_path, 'r') as zf:
                zf.setpassword(password.encode('utf-8'))
                zf.extractall(dest_dir)
        else:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(dest_dir)
        return True, ""
    except RuntimeError as e:
        if "Bad password" in str(e) or "password" in str(e).lower():
            return False, "密码错误"
        return False, f"恢复失败: {str(e)}"
    except zipfile.BadZipFile:
        return False, "备份文件损坏或不是有效的 ZIP 文件"
    except PermissionError:
        return False, "权限不足，无法写入目标目录"
    except Exception as e:
        return False, f"恢复失败: {str(e)}"


def backup_all(sources, dest_dir, password=None):
    """遍历 sources 中已启用的项目执行备份。
    返回结果列表 [{"path", "success", "zip_path", "skipped", "error", "is_file"}]
    """
    if not dest_dir:
        return [{"path": "", "success": False, "zip_path": "", "skipped": [], "error": "未设置备份路径", "is_file": False}]

    results = []

    for src in sources:
        if not src.get("enabled", True):
            continue
        path = src.get("path", "")
        
        is_file = os.path.isfile(path)
        is_dir = os.path.isdir(path)
        
        if not path or (not is_file and not is_dir):
            results.append({
                "path": path or "(空)",
                "success": False,
                "zip_path": "",
                "skipped": [],
                "error": "路径不存在",
                "is_file": False
            })
            continue
        try:
            zip_path, skipped = backup_source(path, dest_dir, password)
            results.append({
                "path": path,
                "success": True,
                "zip_path": zip_path,
                "skipped": skipped,
                "error": "",
                "is_file": is_file
            })
        except Exception as e:
            results.append({
                "path": path,
                "success": False,
                "zip_path": "",
                "skipped": [],
                "error": str(e),
                "is_file": is_file
            })

    return results
