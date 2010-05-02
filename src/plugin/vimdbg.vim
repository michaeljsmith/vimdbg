let s:script_location = expand("<sfile>:h")
let s:script_module = expand("<sfile>:t:r")

exe 'python sys.path.append(r"' . s:script_location . '")'
exe 'python try: reload(' . s:script_module . ")\n" . 'except NameError: pass'
exe 'python import ' . s:script_module
let create_gdb_session_cmd = "try:\n"
let create_gdb_session_cmd .= "\tgdb_session = vimdbg.GdbSession()\n"
let create_gdb_session_cmd .= "except " . s:script_module . ".Error as e:\n"
let create_gdb_session_cmd .= "\tprint \"Dbg Error: \" + e.msg"
exe 'python ' . create_gdb_session_cmd

