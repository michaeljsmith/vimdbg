if exists("s:script_loaded") && s:script_loaded
	exe "python try: gdb_session.shutdown()\n" . 'except NameError: pass'
endif

let s:script_location = expand("<sfile>:h")
let s:script_module = expand("<sfile>:t:r")
let s:script_loaded = 0
let s:debugger_started = 0

if !exists("g:debugger_thread_logging")
	let g:debugger_thread_logging = 0
endif

function! <Sid>DbgCommand(cmd)
	let python_cmd = "try:\n"
	let python_cmd .= "\t" . a:cmd . "\n"
	let python_cmd .= "except " . s:script_module . ".Error, e:\n"
	let python_cmd .= "\tprint \"Dbg Error: \" + e.msg"
	exe 'python ' . python_cmd
endfunction

function! <Sid>LoadPython()
	exe 'python import sys'
	exe 'python sys.path.append(r"' . s:script_location . '")'
	exe 'python try: reload(' . s:script_module . ")\n" . 'except NameError: pass'
	exe 'python import ' . s:script_module
	exe 'python vimdbg.thread_logging = ' . g:debugger_thread_logging
endfunction

function! <Sid>GdbInitialize()
	call <Sid>DbgCommand("next_bp_id = 1")
	call <Sid>DbgCommand("breakpoints = vimdbg.BreakpointCollection()")
	call <Sid>DbgCommand("gdb_driver = vimdbg.GdbDriver()")
	call <Sid>DbgCommand("gdb_session = vimdbg.Session(gdb_driver, breakpoints)")
endfunction

function! <Sid>GdbEnsureLoaded()
	if !s:script_loaded
		call <Sid>LoadPython()
		call <Sid>GdbInitialize()
		let s:script_loaded = 1
	endif
endfunction

function! <Sid>GdbEnsureStarted()
	call <Sid>GdbEnsureLoaded()
	if !s:debugger_started
		call GdbStart()
	endif
endfunction

function! GdbStart()
	call <Sid>GdbEnsureLoaded()
	if !s:debugger_started
		call <Sid>DbgCommand("gdb_session.display_log_window()")
		call <Sid>DbgCommand("gdb_session.start_debugger()")

		augroup DbgCleanup
		autocmd VimLeave * call GdbStop()
		augroup end
		let s:debugger_started = 1
	endif
endfunction

function! GdbFile(file)
	call <Sid>GdbEnsureStarted()
	call <Sid>DbgCommand("gdb_driver.set_file('" . a:file . "')")
endfunction

function! GdbRun()
	call <Sid>GdbEnsureStarted()
	call <Sid>DbgCommand("gdb_session.run_debugger()")
endfunction

function! GdbStop()
	if s:debugger_started
		call <Sid>DbgCommand("gdb_session.shutdown()")

		autocmd! DbgCleanup
		let s:debugger_started = 0
	endif
endfunction

function! GdbUpdate()
	call <Sid>GdbEnsureStarted()
	call <Sid>DbgCommand("gdb_session.update()")
endfunction

function! GdbBreakpoint(file, line)
	call <Sid>GdbEnsureLoaded()
	let cmd = "breakpoints.add(next_bp_id, '" . a:file . "', " . a:line . ")"
	call <Sid>DbgCommand(cmd)
	call <Sid>DbgCommand("next_bp_id += 1")
endfunction
