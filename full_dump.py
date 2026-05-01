import os

def generate_data_dump(target_folder, output_file):
    # قائمة بالملفات التي نريد تجاهلها تماماً
    exclude_files = [output_file, 'full_dump.py']
    
    # التأكد من وجود المجلد المستهدف
    if not os.path.exists(target_folder):
        print(f"❌ خطأ: المجلد '{target_folder}' غير موجود!")
        return

    with open(output_file, 'w', encoding='utf-8') as f_out:
        f_out.write(f"=== FOLDER STRUCTURE: {target_folder} (INCLUDING EMPTY DIRS) ===\n")
        
        # 1. رسم الشجرة لمجلد data فقط
        for root, dirs, files in os.walk(target_folder):
            level = root.replace(target_folder, '').count(os.sep)
            indent = ' ' * 4 * level
            f_out.write(f"{indent}{os.path.basename(root)}/\n")
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                if f not in exclude_files:
                    f_out.write(f"{subindent}{f}\n")
        
        f_out.write("\n" + "="*50 + "\n")
        f_out.write(f"=== CONTENTS OF: {target_folder} ===\n")
        f_out.write("="*50 + "\n\n")

        # 2. قراءة الملفات داخل مجلد data فقط
        for root, dirs, files in os.walk(target_folder):
            for file in files:
                if file in exclude_files: continue
                
                file_path = os.path.join(root, file)
                # جعل المسار المعروض يبدأ من داخل المجلد المستهدف
                rel_path = os.path.relpath(file_path, target_folder)
                
                f_out.write(f'--- START OF FILE: {rel_path} ---\n')
                try:
                    with open(file_path, 'r', encoding='utf-8') as f_in:
                        f_out.write(f_in.read())
                except (UnicodeDecodeError, PermissionError):
                    f_out.write(f"[Binary/Media File: Content not readable as text]")
                f_out.write(f'\n--- END OF FILE: {rel_path} ---\n\n')

if __name__ == "__main__":
    # حدد هنا اسم المجلد الذي تريد جرده (مثلاً 'data' أو 'pipeline/data')
    TARGET = 'data' 
    OUTPUT = 'data_snapshot.txt'
    
    generate_data_dump(TARGET, OUTPUT)
    print(f"✅ تم جرد مجلد '{TARGET}' بنجاح في ملف: {OUTPUT}")