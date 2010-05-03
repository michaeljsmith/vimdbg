let s:script_location = expand("<sfile>:h")
let s:script_module = expand("<sfile>:t:r")

function! <Sid>DbgCommand(cmd)
	let python_cmd = "try:\n"
	let python_cmd .= "\t" . a:cmd . "\n"
	let python_cmd .= "except " . s:script_module . ".Error as e:\n"
	let python_cmd .= "\tprint \"Dbg Error: \" + e.msg"
	exe 'python ' . python_cmd
endfunction

function! <Sid>LoadPython()
	exe "python try: gdb_session.shutdown()\n" . 'except NameError: pass'
	exe 'python sys.path.append(r"' . s:script_location . '")'
	exe 'python try: reload(' . s:script_module . ")\n" . 'except NameError: pass'
	exe 'python import ' . s:script_module
endfunction

function! GdbStart()
	call <Sid>LoadPython()
	call <Sid>DbgCommand("next_bp_id = 1")
	call <Sid>DbgCommand("breakpoints = vimdbg.BreakpointCollection()")
	call <Sid>DbgCommand("gdb_driver = vimdbg.GdbDriver()")
	call <Sid>DbgCommand("gdb_session = vimdbg.Session(gdb_driver, breakpoints)")
	call <Sid>DbgCommand("gdb_session.display_log_window()")
	call <Sid>DbgCommand("gdb_session.start_debugger()")
endfunction

function! GdbFile(file)
	call <Sid>DbgCommand("gdb_driver.set_file('" . a:file . "')")
endfunction

function! GdbRun()
	call <Sid>DbgCommand("gdb_session.run_debugger()")
endfunction

function! GdbStop()
	call <Sid>DbgCommand("gdb_session.shutdown()")
endfunction

function! GdbUpdate()
	call <Sid>DbgCommand("gdb_session.update()")
endfunction

function! GdbBreakpoint(file, line)
	python print id(breakpoints)
	let cmd = "breakpoints.add(next_bp_id, '" . a:file . "', " . a:line . ")"
	call <Sid>DbgCommand(cmd)
	call <Sid>DbgCommand("next_bp_id += 1")
endfunction
