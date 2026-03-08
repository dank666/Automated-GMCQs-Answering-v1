import re
import os

def get_condition_attribute_count():
    """
    从 decision_formal_context_condition.txt 文件中读取条件属性数量
    第一行是对象数量，第二行是条件属性数量
    """
    condition_file = os.path.join('test_contexts', 'decision_formal_context_condition.txt')
    try:
        with open(condition_file, 'r', encoding='utf-8') as f:
            f.readline()  # 跳过第一行（对象数量）
            second_line = f.readline().strip()  # 读取第二行（条件属性数量）
            return int(second_line)
    except FileNotFoundError:
        print(f"错误：找不到条件属性文件 {condition_file}")
        return 26  # 默认值
    except ValueError:
        print("错误：无法解析条件属性数量")
        return 26  # 默认值

def process_file(file_path, offset=None):
    """
    处理结果文件，将#后面的数字都加上条件属性数量
    """
    # 如果没有指定offset，则自动获取
    if offset is None:
        offset = get_condition_attribute_count()
        print(f"检测到条件属性数量: {offset}")
    
    try:
        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 处理每一行
        lines = content.split('\n')
        processed_lines = []
        
        for line in lines:
            if '#' in line:
                # 分割#前后的内容
                parts = line.split('#', 1)
                before_hash = parts[0]
                after_hash = parts[1]
                
                # 只处理#后面的数字，将每个数字加上offset
                def add_offset(match):
                    return str(int(match.group()) + offset)
                
                processed_after = re.sub(r'\b\d+\b', add_offset, after_hash)
                processed_line = before_hash + '#' + processed_after
                processed_lines.append(processed_line)
            else:
                processed_lines.append(line)
        
        # 生成输出文件名
        if file_path.endswith('.txt'):
            output_path = file_path[:-4] + '_processed.txt'
        else:
            output_path = file_path + '_processed'
        
        # 保存处理后的文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(processed_lines))
        
        print(f"处理完成！已保存到: {output_path}")
        
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
    except Exception as e:
        print(f"处理文件时出错: {e}")

if __name__ == "__main__":
    import sys
    
    # 默认自动模式，处理固定文件
    file_path = os.path.join('test_results', 'threeWcl_decision.txt')
    print(f"自动处理文件: {file_path}")
    process_file(file_path)