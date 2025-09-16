import argparse
import sys
import os
import fractions

def parse_args():

    # define args
    parser = argparse.ArgumentParser(description='Maidata diff tool, v0.1.0')
    parser.add_argument('-lv', type=int, choices=range(2, 8), help='inote level (2-7)')
    parser.add_argument('-txt1', type=str, help='Path to txt 1')
    parser.add_argument('-txt2', type=str, help='Path to txt 2')
    parser.add_argument('positional', nargs='*', help='Positional args: level path1 path2')
    args = parser.parse_args()
    
    lv = None
    txt1 = None
    txt2 = None
    
    # parse args
    if args.lv and args.txt1 and args.txt2:
        lv = args.lv
        txt1 = args.txt1
        txt2 = args.txt2
    elif len(args.positional) == 3:
        lv = args.positional[0]
        txt1 = args.positional[1]
        txt2 = args.positional[2]
    elif len(args.positional) == 0 and not args.lv and not args.txt1 and not args.txt2:
        # 没有任何参数时，分别询问用户输入
        print("Please provide the following parameters:")
        lv = input("Enter inote level (2-7): ").strip()
        txt1 = input("Enter path to txt file 1: ").strip()
        txt2 = input("Enter path to txt file 2: ").strip()
        if txt1.startswith('"') and txt1.endswith('"'):
            txt1 = txt1[1:-1]
        if txt2.startswith('"') and txt2.endswith('"'):
            txt2 = txt2[1:-1]
    else:
        print("args error: invalid args")
        print("-----------")
        parser.print_help()
        print("\ndiff output format: 'note1' bpm_length")
        print(f"{19 * ' '} 'note2' bpm_length\n")
        sys.exit(1)

    # validate args
    try:
        if not (2 <= int(lv) <= 7): raise ValueError
    except ValueError:
        print(f"args error: inote level must be int 2-7")
        sys.exit(1)
    if not os.path.exists(txt1):
        print(f"args error: txt1 not exist")
        sys.exit(1)
    if not os.path.exists(txt2):
        print(f"args error: txt2 not exist")
        sys.exit(1)
    
    return lv, txt1, txt2



def get_inote(lv, txt, txt_num):

    with open(txt, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    target_inote = f"&inote_{lv}="
    inote_content = []
    found = False
    start_line = None
    line_mapping = []  # 记录每个字符对应的行号
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line: continue
        if line.startswith('||'): continue # Skip comment

        # Find the target inote
        if not found and line.startswith(target_inote):
            found = True
            start_line = line_num
            content = line[len(target_inote):].strip()
            if content:
                inote_content.append(content)
                # 为这部分内容的每个字符记录行号
                for _ in content:
                    line_mapping.append(line_num)
            continue
        # If we found the target inote and encounter another inote, stop
        if found and line.startswith('&inote_'):
            break
        # Append line to inote
        if found:
            inote_content.append(line)
            # 为这行内容的每个字符记录行号
            for _ in line:
                line_mapping.append(line_num)
            continue
    
    if not found:
        print(f"get_inote error: inote_{lv} not found in {txt_num}")
        sys.exit(1)

    return ''.join(inote_content).replace('\n', ''), start_line, line_mapping



def get_line_number_for_position(line_mapping, position):

    if position < 0 or position >= len(line_mapping):
        return None
    return line_mapping[position]



def translate_inote(inote):

    segments = inote.split(',')
    result = []
    current_bpm = None
    current_length = None
    added_initial_placeholder = False
    
    i = 0
    while i < len(segments):
        segment = segments[i].strip()
        if segment == 'E': break  # End of inote
        note_info, current_bpm, current_length = parse_bpm_length(segment, current_bpm, current_length, i)

        # 开头默认添加一个时长为0的占位符
        if not added_initial_placeholder and current_bpm is not None and current_length is not None:
            result.append({
                'info': '@',
                'bpm': current_bpm,
                'length': fractions.Fraction(0, 1),
                'segment_index': -1  # 特殊标记为开头占位符
            })
            added_initial_placeholder = True
        
        if note_info:
            # Parse this segment as notes
            parsed_note = parse_note_segment(note_info, current_bpm, current_length)
            if parsed_note:
                # Add segment index for context tracking
                if isinstance(parsed_note, dict):
                    parsed_note['segment_index'] = i
                elif isinstance(parsed_note, list):
                    for note in parsed_note:
                        note['segment_index'] = i
                result.append(parsed_note)
        else:
            # No info segment means placeholder note '@'
            # Loop check if next segment also no info
            # Combine consecutive placeholder notes into one
            placeholder_length = fractions.Fraction(1, current_length)
            j = i + 1
            if j >= len(segments): break # End of inote

            while j < len(segments):
                next_segment = segments[j].strip()
                if next_segment == 'E': break # End of inote
                note_info, current_bpm, current_length = parse_bpm_length(next_segment, current_bpm, current_length, j)
                
                if note_info: break # Not a placeholder segment
                placeholder_length += fractions.Fraction(1, current_length) # Add placeholder segment
                j += 1
            
            # Add combined length to last note
            if result:
                # If last note is a single note
                if isinstance(result[-1], dict):
                    result[-1]['length'] += placeholder_length
                # If last note is a list (simultaneous notes)    
                elif isinstance(result[-1], list):
                    for note in result[-1]:
                        note['length'] += placeholder_length
            else:
                # If no notes yet, create a placeholder note
                result.append({
                    'info': '@',
                    'bpm': current_bpm,
                    'length': placeholder_length,
                    'segment_index': i
                })

            i = j - 1  # j-1 because will i++ below
        
        i += 1
    
    # 修改最后一个note的delay为0（特殊情况处理）
    if result and len(result) > 1:  # 确保有note并且不只是开头的占位符
        last_note = result[-1]
        if isinstance(last_note, dict):
            # 单个note
            if last_note['info'] != '@':  # 不是占位符
                last_note['length'] = fractions.Fraction(0, 1)
        elif isinstance(last_note, list):
            # 同时的多个notes
            for note in last_note:
                if note['info'] != '@':  # 不是占位符
                    note['length'] = fractions.Fraction(0, 1)
    
    return result



def get_context_from_original(inote_raw, segment_index, context_chars=20):

    if segment_index < 0:  # 开头占位符
        return inote_raw[:context_chars*2] if len(inote_raw) > context_chars*2 else inote_raw
    
    segments = inote_raw.split(',')
    if segment_index >= len(segments):
        return ""
    
    # 找到目标segment在原始字符串中的位置
    current_pos = 0
    for i in range(segment_index):
        current_pos += len(segments[i]) + 1  # +1 for comma
    
    # 获取目标segment
    target_segment = segments[segment_index]
    segment_start = current_pos
    segment_end = current_pos + len(target_segment)
    
    # 获取前后context_chars个字符
    context_start = max(0, segment_start - context_chars)
    context_end = min(len(inote_raw), segment_end + context_chars)
    
    context = inote_raw[context_start:context_end]
    # 标记目标segment的位置
    relative_start = segment_start - context_start
    relative_end = segment_end - context_start
    
    if relative_start >= 0 and relative_end <= len(context):
        context = (context[:relative_start] + 
                  ">>>" + context[relative_start:relative_end] + "<<<" + 
                  context[relative_end:])
    
    return context



def parse_bpm_length(segment, current_bpm, current_length, i):
    
    # Parse BPM and length settings from this segment
    while True:
        bpm_updated = False
        length_updated = False
        
        # Parse BPM (xxx)
        if '(' in segment:
            start = segment.find('(')
            end = segment.find(')', start)
            if end != -1:
                current_bpm = int(segment[start+1:end])
                segment = segment[:start] + segment[end+1:]
                bpm_updated = True
        
        # Parse length {xxx}
        if '{' in segment:
            start = segment.find('{')
            end = segment.find('}', start)
            if end != -1:
                current_length = int(segment[start+1:end])
                segment = segment[:start] + segment[end+1:]
                length_updated = True
        
        if not bpm_updated and not length_updated:
            break
    
    # Remove BPM and length settings, leaving only note info
    note_info = segment.strip()

    if current_bpm is None or current_length is None:
        print(f"parse_bpm_length error: BPM not set at note {i}")
        sys.exit(1)

    return note_info, current_bpm, current_length



def parse_note_segment(segment, current_bpm, current_length):

    if not segment: return None

    if "`" in segment:
        segment.replace("`", "`/") # Parse as simultaneous notes
    if "/" in segment:
        # Split by '/' for simultaneous notes
        simultaneous_notes = segment.split('/')
    else:
        # Further check if '/' omitted for tap notes
        # e.g. "123" means 1/2/3
        try:
            if int(segment) >= 10:
                # Split multi-digit number into individual digits
                simultaneous_notes = list(segment)
            else:
                # Single note
                return parse_single_note(segment, current_bpm, current_length)
        except ValueError:
            # Single note
            return parse_single_note(segment, current_bpm, current_length)
    
    notes = []
    for note_str in simultaneous_notes:
        note = parse_single_note(note_str.strip(), current_bpm, current_length)
        if note:
            notes.append(note)
    if notes: notes.sort(key=lambda x: x['info'])

    return notes if notes else None



def parse_single_note(note_str, current_bpm, current_length):

    note_str = note_str.strip()
    if not note_str: return None
    info = note_str
    
    # Check for [x:x] hold
    hold = fractions.Fraction(0)
    while '[' in info:
        start_bracket = info.find('[')
        end_bracket = info.find(']', start_bracket)
        if end_bracket != -1:
            length_part = info[start_bracket+1:end_bracket]

            if ':' in length_part:
                parts = length_part.split(':')
                if len(parts) == 2:
                    try:
                        denominator = int(parts[0])
                        numerator = int(parts[1])
                        hold += fractions.Fraction(numerator, denominator)
                    except ValueError:
                        print(f"parse_single_note error: Invalid [content] in '{note_str}'")
            
            # Remove the length part from info
            info = info[:start_bracket] + info[end_bracket+1:]
    
    # Use length override if present
    if hold != fractions.Fraction(0):
        return {
            'info': info.strip(),
            'bpm': current_bpm,
            'length': fractions.Fraction(1, current_length),
            'hold': hold
        }
    # Otherwise use current length
    else:
        return {
            'info': info.strip(),
            'bpm': current_bpm,
            'length': fractions.Fraction(1, current_length)
        }
    


def compare_inotes(inote1_trans, inote2_trans, inote1_raw, inote2_raw, start_line1, start_line2, txt1, txt2, line_mapping1, line_mapping2):

    def note_str(note):
        if note.get('hold'):
            note_str = f"'{note['info']}[{note['hold']}]': bpm-{note['bpm']}, delay-{note['length']}"
        else:
            note_str = f"'{note['info']}': bpm-{note['bpm']}, delay-{note['length']}"
        return note_str
    
    if inote1_trans == inote2_trans:
        print("No difference found.")
        return
    
    # 收集所有错误
    errors = []
    
    max_len = max(len(inote1_trans), len(inote2_trans))
    for i in range(max_len):
        note1 = inote1_trans[i] if i < len(inote1_trans) else None
        note2 = inote2_trans[i] if i < len(inote2_trans) else None
        
        if note1 != note2:

            if note1:
                if isinstance(note1, dict):
                    note1_str = note_str(note1)
                    segment_idx1 = note1.get('segment_index', -1)
                elif isinstance(note1, list):
                    note1_str = ', '.join(note_str(n) for n in note1)
                    segment_idx1 = note1[0].get('segment_index', -1) if note1 else -1
            else:
                note1_str = "None"
                segment_idx1 = -1
            
            if note2:
                if isinstance(note2, dict):
                    note2_str = note_str(note2)
                    segment_idx2 = note2.get('segment_index', -1)
                elif isinstance(note2, list):
                    note2_str = ', '.join(note_str(n) for n in note2)
                    segment_idx2 = note2[0].get('segment_index', -1) if note2 else -1
            else:
                note2_str = "None"
                segment_idx2 = -1

            # further handle diff
            note1_str_norm = note1_str.replace("c1", "C").replace("c2", "C").replace("C1", "C")
            note2_str_norm = note2_str.replace("c1", "C").replace("c2", "C").replace("C1", "C")
            note1_str_norm = note1_str_norm.replace("xh", "hx").replace("xb", "bx").replace("hb", "bh")
            note2_str_norm = note2_str_norm.replace("xh", "hx").replace("xb", "bx").replace("hb", "bh")
            note1_str_norm = note1_str_norm.replace(">", "^").replace("<", "^")
            note2_str_norm = note2_str_norm.replace(">", "^").replace("<", "^")
            note1_str_norm = note1_str_norm.replace("$", "")
            note2_str_norm = note2_str_norm.replace("$", "")
            
            if note1_str_norm == note2_str_norm:
                continue

            # 计算错误在原始字符串中的位置
            pos1 = get_segment_position(inote1_raw, segment_idx1)
            pos2 = get_segment_position(inote2_raw, segment_idx2)
            
            errors.append({
                'diff_index': i,
                'note1_str': note1_str,
                'note2_str': note2_str,
                'segment_idx1': segment_idx1,
                'segment_idx2': segment_idx2,
                'pos1': pos1,
                'pos2': pos2
            })

            # if i > 200: break

    if not errors:
        print("No difference found.")
        return

    # 分组处理错误 - 基于位置相近性
    grouped_errors = group_nearby_errors(errors)
    
    # 打印分组的错误
    for group_idx, error_group in enumerate(grouped_errors):
        print_error_group(error_group, group_idx, inote1_raw, inote2_raw, start_line1, start_line2, txt1, txt2, line_mapping1, line_mapping2)

    print(f"Reach end of inote.")

    # # Ask user to continue
    # while True:
    #     user_input = input("Stop comparing? (y/n): ").strip().lower()
    #     if user_input == 'y':
    #         print(f"Comparison stopped.")
    #         return
    #     else:
    #         # Move cursor up one line and clear it to overwrite the prompt
    #         print("\033[A\033[K", end="")
    #         break



def get_segment_position(inote_raw, segment_index):

    if segment_index < 0:
        return 0
    
    segments = inote_raw.split(',')
    if segment_index >= len(segments):
        return len(inote_raw)
    
    current_pos = 0
    for i in range(segment_index):
        current_pos += len(segments[i]) + 1  # +1 for comma
    
    return current_pos



def group_nearby_errors(errors, max_distance=6):

    if not errors:
        return []
    
    # 按位置排序
    errors.sort(key=lambda x: min(x['pos1'], x['pos2']))
    
    groups = []
    current_group = [errors[0]]
    
    for i in range(1, len(errors)):
        curr_error = errors[i]
        last_error = current_group[-1]
        
        # 检查是否相近（基于两个文件中的最小距离）
        dist1 = abs(curr_error['pos1'] - last_error['pos1'])
        dist2 = abs(curr_error['pos2'] - last_error['pos2'])
        min_distance = min(dist1, dist2)
        
        if min_distance <= max_distance:
            current_group.append(curr_error)
        else:
            groups.append(current_group)
            current_group = [curr_error]
    
    groups.append(current_group)
    return groups



def print_error_group(error_group, group_idx, inote1_raw, inote2_raw, start_line1, start_line2, txt1, txt2, line_mapping1, line_mapping2):

    # 计算合适的上下文范围
    all_positions1 = [err['pos1'] for err in error_group]
    all_positions2 = [err['pos2'] for err in error_group]
    
    context_chars = 20
    
    # 为文件生成上下文
    context1, markers1 = get_context_with_markers(inote1_raw, error_group, 'pos1', 'segment_idx1', context_chars)
    context2, markers2 = get_context_with_markers(inote2_raw, error_group, 'pos2', 'segment_idx2', context_chars)
    
    # 获取实际行号
    actual_line1 = get_line_number_for_position(line_mapping1, min(all_positions1)) or start_line1
    actual_line2 = get_line_number_for_position(line_mapping2, min(all_positions2)) or start_line2
    
    # 对齐行号 (使用后置空格填充)
    line1_str = str(actual_line1) + " " * (3 - len(str(actual_line1)))
    line2_str = str(actual_line2) + " " * (3 - len(str(actual_line2)))

    print(f"Error group {group_idx + 1}:")
    print(f"  Line {line1_str}: {context1}")
    print(f"            {markers1}")
    for err in error_group:
        print(f"    diff{err['diff_index']}: {err['note1_str']}")
    
    print(f"\n  Line {line2_str}: {context2}")
    print(f"            {markers2}")
    for err in error_group:
        print(f"    diff{err['diff_index']}: {err['note2_str']}")
    print()



def get_context_with_markers(inote_raw, error_group, pos_key, segment_key, context_chars=20):

    positions = [err[pos_key] for err in error_group]
    segment_indices = [err[segment_key] for err in error_group]
    
    if not positions:
        return "", ""
    
    min_pos = min(positions)
    max_pos = max(positions)
    
    # 计算上下文范围
    context_start = max(0, min_pos - context_chars)
    
    # 需要考虑最长的segment来确定context_end
    segments = inote_raw.split(',')
    max_segment_end = max_pos
    for pos, segment_idx in zip(positions, segment_indices):
        if segment_idx >= 0 and segment_idx < len(segments):
            segment_end = pos + len(segments[segment_idx])
            max_segment_end = max(max_segment_end, segment_end)
    
    context_end = min(len(inote_raw), max_segment_end + context_chars)
    
    context = inote_raw[context_start:context_end]
    
    # 生成标记行
    markers = [' '] * len(context)
    
    for i, (pos, segment_idx) in enumerate(zip(positions, segment_indices)):
        if segment_idx < 0:  # 开头占位符
            continue
        if segment_idx >= len(segments):
            continue
            
        # 计算segment在原始字符串中的实际范围
        segment_start_in_raw = pos
        segment_end_in_raw = pos + len(segments[segment_idx])
        
        # 计算在context中的相对位置
        relative_start = segment_start_in_raw - context_start
        relative_end = segment_end_in_raw - context_start
        
        # 确保边界正确
        relative_start = max(0, relative_start)
        relative_end = min(len(context), relative_end)
        
        # 在标记行中标记这个segment
        if relative_start < len(markers) and relative_end > 0:
            for j in range(relative_start, relative_end):
                if 0 <= j < len(markers):
                    markers[j] = '^'
    
    return context, ''.join(markers)



def main():

    lv, txt1, txt2 = parse_args()

    inote1_raw, start_line1, line_mapping1 = get_inote(lv, txt1, 1)
    inote2_raw, start_line2, line_mapping2 = get_inote(lv, txt2, 2)
    inote1_trans = translate_inote(inote1_raw)
    inote2_trans = translate_inote(inote2_raw)
    compare_inotes(inote1_trans, inote2_trans, inote1_raw, inote2_raw, start_line1, start_line2, txt1, txt2, line_mapping1, line_mapping2)


if __name__ == "__main__":
    main()
