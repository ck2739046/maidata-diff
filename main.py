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
    
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('||'): continue # Skip comment

        # Find the target inote
        if not found and line.startswith(target_inote):
            found = True
            content = line[len(target_inote):].strip()
            if content:
                inote_content.append(content)
            continue
        # If we found the target inote and encounter another inote, stop
        if found and line.startswith('&inote_'):
            break
        # Append line to inote
        if found:
            inote_content.append(line)
            continue
    
    if not found:
        print(f"get_inote error: inote_{lv} not found in {txt_num}")
        sys.exit(1)

    return ''.join(inote_content).replace('\n', '')



def translate_inote(inote):

    segments = inote.split(',')
    result = []
    current_bpm = None
    current_length = None
    
    i = 0
    while i < len(segments):
        segment = segments[i].strip()
        if segment == 'E': break  # End of inote
        note_info, current_bpm, current_length = parse_bpm_length(segment, current_bpm, current_length, i)
        
        if note_info:
            # Parse this segment as notes
            parsed_note = parse_note_segment(note_info, current_bpm, current_length)
            if parsed_note:
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
                })

            i = j - 1  # j-1 because will i++ below
        
        i += 1
    
    return result



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
    


def compare_inotes(inote1, inote2):

    def note_str(note):
        if note.get('hold'):
            note_str = f"'{note['info']}[{note['hold']}]' {note['bpm']}_{note['length']}"
        else:
            note_str = f"'{note['info']}' {note['bpm']}_{note['length']}"
        return note_str
    
    if inote1 == inote2:
        print("No differnce found.")
        return
    
    max_len = max(len(inote1), len(inote2))
    for i in range(max_len):
        note1 = inote1[i] if i < len(inote1) else None
        note2 = inote2[i] if i < len(inote2) else None
        
        if note1 != note2:

            if isinstance(note1, dict):
                note1_str = note_str(note1)
            elif isinstance(note1, list):
                note1_str = ', '.join(note_str(n) for n in note1)
            
            if isinstance(note2, dict):
                note2_str = note_str(note2)
            elif isinstance(note2, list):
                note2_str = ', '.join(note_str(n) for n in note2)


            # further handle diff
            note1_strr = note1_str.lower()
            note2_strr = note2_str.lower()
            # ch c1h c2h
            note1_strr = note1_strr.replace("c1h", "ch")
            note2_strr = note2_strr.replace("c1h", "ch")
            note1_strr = note1_strr.replace("c2h", "ch")
            note2_strr = note2_strr.replace("c2h", "ch")
            # xh hx
            note1_strr = note1_strr.replace("xh", "hx")
            note2_strr = note2_strr.replace("xh", "hx")
            # > < ^
            note1_strr = note1_strr.replace(">", "^")
            note2_strr = note2_strr.replace(">", "^")
            note1_strr = note1_strr.replace("<", "^")
            note2_strr = note2_strr.replace("<", "^")
            # treat as same
            if note1_strr == note2_strr:
                continue


            print(f"diff{i}: {note1_str}\n" +
                  f"{(6+len(str(i))) * ' '}" +
                  f"{note2_str}")
            
            # Ask user to continue
            while True:
                user_input = input("Stop comparing? (y/n): ").strip().lower()
                if user_input == 'y':
                    print(f"Comparison stopped.")
                    return
                else:
                    # Move cursor up one line and clear it to overwrite the prompt
                    print("\033[A\033[K", end="")
                    break
    
    print(f"Reach end if inote.")



def main():

    lv, txt1, txt2 = parse_args()
    inote1 = get_inote(lv, txt1, 1)
    inote2 = get_inote(lv, txt2, 2)
    inote1_trans = translate_inote(inote1)
    inote2_trans = translate_inote(inote2)
    compare_inotes(inote1_trans, inote2_trans)
    

if __name__ == "__main__":
    main()
