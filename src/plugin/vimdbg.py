import vim
import subprocess
import threading

class Error(Exception): pass

class CreateBufferError(Error):
	def __init__(self, msg): self.msg = msg

class BufferMissingError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerMissingError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerSpawnError(Error):
	def __init__(self, msg): self.msg = msg

class QueueEmptyError(Error):
	def __init__(self, msg): self.msg = msg

class QueueCorruptError(Error):
	def __init__(self, msg): self.msg = msg

class ThreadNotRunningError(Error):
	def __init__(self, msg): self.msg = msg

class ThreadAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class DebuggerStdoutClosed(Error):
	def __init__(self, msg): self.msg = msg

class DriverBreakpointsAlreadyConnectedError(Error):
	def __init__(self, msg): self.msg = msg

class DriverBreakpointsNotConnectedError(Error):
	def __init__(self, msg): self.msg = msg

class DriverAlreadyRunningError(Error):
	def __init__(self, msg): self.msg = msg

class BreakpointMissingError(Error):
	def __init__(self, msg): self.msg = msg

class BreakpointAlreadyExistsError(Error):
	def __init__(self, msg): self.msg = msg

class Delegate(object):
	def __init__(self):
		self.hndlrs = {}

	def add_handler(self, id, hndlr):
		self.hndlrs[id] = hndlr

	def remove_handler(self, id):
		del self.hndlrs[i]

	def signal(self, *args):
		for hndlr in self.hndlrs.itervalues():
			hndlr(*args)

class ThreadMessageQueue(object):
	def __init__(self):
		self.items = []
		self.lock = threading.Lock()

	def append(self, message):
		self.lock.acquire()
		try:
			self.items.append(message)
		finally:
			self.lock.release()

	def pop(self):
		self.lock.acquire()
		message = None
		try:
			message = self.items.pop(0)
		finally:
			self.lock.release()
		return message

	def empty(self):
		self.lock.acquire()
		try:
			l = len(self.items)
		finally:
			self.lock.release()
		return l == 0

session_id = 100
def get_session_id():
	global session_id
	new_session_id = session_id
	session_id += 1
	return new_session_id

class Session(object):
	def __init__(self, driver, bps):
		self.session_id = get_session_id()
		self.driver = driver
		self.driver_proxy = DriverProxy(driver)
		self.log_window = LogWindow(self.session_id)
		self.thread = None
		self.message_queue = ThreadMessageQueue()
		self.bps = bps
		self.driver_connected_to_bps = False

		# Display all communications in the log window.
		self.driver_proxy.on_communication.add_handler(
				self.log_window, self.log_window.log_message)
		self.driver.on_log.add_handler(
				self.log_window, self.log_window.log_message)

		# Log all breakpoint operations.
		def log_breakpoint_add(id, file, line):
			self.log_window.log_message(
					"Breakpoint added(" + str(id) + "): " +
					file + "(" + str(line) + ")")
		def log_breakpoint_remove(id, file, line):
			self.log_window.log_message(
					"Breakpoint removed(" + str(id) + "): " +
					file + "(" + str(line) + ")")
		self.bps.on_add.add_handler(self.log_window, log_breakpoint_add)
		self.bps.on_remove.add_handler(self.log_window, log_breakpoint_remove)

	def display_log_window(self):
		self.log_window.create_buffer()
		self.log_window.display()
		self.log_window.log_message("bps = " + str(id(self.bps)))

	def start_debugger(self):
		self.log_window.log_message("Starting debugger.\n")
		if self.thread:
			raise ThreadAlreadyRunningError(
					'Cannot start listen thread - already running.')

		self.driver_proxy.start()

		driver = self.driver
		message_queue = self.message_queue
		class Thread(threading.Thread):
			def run(self):
				driver.listen(message_queue)
		self.thread = Thread()
		self.thread.start()

	def stop_debugger(self):
		self.log_window.log_message("Stopping debugger.")
		if self.driver_connected_to_bps:
			self.disconnect_driver_from_breakpoints()
		if not self.thread:
			raise ThreadNotRunningError(
					'Cannot stop debugger - listen thread not running.')
		self.driver_proxy.stop()
		self.thread.join()
		self.driver_proxy.read_all_pending(self.message_queue)

	def run_debugger(self):
		if not self.driver_connected_to_bps:
			self.connect_driver_to_breakpoints()
		self.log_window.log_message("Running debugger.\n")
		self.driver_proxy.run()

	def shutdown(self):
		try:
			self.stop_debugger()
		except DebuggerMissingError: pass

	def update(self):
		if not self.thread:
			raise ThreadNotRunningError(
					'Cannot update dbg thread - listen thread not running.')
		self.driver_proxy.read_all_pending(self.message_queue)

	def connect_driver_to_breakpoints(self):
		if self.driver_connected_to_bps:
			raise DriverBreakpointsAlreadyConnectedError(
					"Cannot connect driver to breakpoints - already connected.")
		self.log_window.log_message('Connecting breakpoings.' + str(self.bps.bps))
		self.bps.on_add.add_handler(self.driver_proxy, self.driver_proxy.add_breakpoint)
		self.bps.on_remove.add_handler(self.driver_proxy, self.driver_proxy.remove_breakpoint)
		for id, (file, line) in self.bps.bps.iteritems():
			self.driver_proxy.add_breakpoint(id, file, line)
		self.driver_connected_to_bps = True

	def disconnect_driver_from_breakpoints(self):
		if not self.driver_connected_to_bps:
			raise DriverBreakpointsNotConnectedError(
					"Cannot disconnect driver from breakpoints - not connected.")
		self.bps.on_add.remove_handler(self.driver_proxy)
		self.bps.on_remove.remove_handler(self.driver_proxy)
		for id, (drvr_id, file, line) in self.driver_proxy.bps.iteritems():
			self.driver_proxy.remove_breakpoint(id)
		self.driver_connected_to_bps = False

class DriverProxy(object):
	def __init__(self, driver):
		self.driver = driver
		self.on_communication = Delegate()
	
	def read(self, queue):
		try:
			msg = queue.pop()
		except IndexError:
			raise QueueEmptyError('Tried to read from empty thread queue.')
		meth, args = msg
		try:
			f = getattr(self, meth)
		except AttributeError:
			raise QueueCorruptError('Unknown method "' + meth + '".')
		try:
			f(*args)
		except TypeError as e:
			raise QueueCorruptError('Invalid args in queue: "' + e.msg + '".')

	def read_all_pending(self, queue):
		while not queue.empty():
			self.read(queue)

	def handle_communication(self, msg):
		self.on_communication.signal(msg)

	def handle_eof(self):
		print "Debugger process exitted."

	def start(self):
		self.driver.start()

	def stop(self):
		self.driver.stop()

	def run(self):
		self.driver.run()

	def set_file(self, file):
		self.driver.set_file(file)

	def add_breakpoint(self, id, file, line):
		self.driver.add_breakpoint(id, file, line)

	def remove_breakpoint(self, id):
		self.driver.remove_breakpoint(id)

class GdbDriver(object):
	def __init__(self):
		self.process = None
		self.running = False
		self.on_log = Delegate()

	def start(self):
		if self.process:
			raise DebuggerAlreadyRunningError(
					"Cannot start debugger: GDB is already running.")
		try:
			self.process = subprocess.Popen("gdb --interpreter mi", shell=True, bufsize=1,
					stdin=subprocess.PIPE, stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT)
		except OSError as e:
			raise DebuggerSpawnError("Failed to start GDB: " + e.strerror)

	def stop(self):
		if not self.process:
			raise DebuggerMissingError("Cannot stop debugger: GDB not running.")
		self.process.stdin.close()
		self.process.wait()

	def run(self):
		if not self.process:
			raise DebuggerMissingError("Cannot run debugger: GDB not running.")
		if self.running:
			raise DriverAlreadyRunningError("Cannot start debugging: already debugging.")
		self.process.stdin.write('-exec-run\n')

	def set_file(self, file):
		self.on_log.signal("Setting debug file: " + file + "\n")
		if not self.process:
			raise DebuggerMissingError("Cannot set file: GDB not running.")
		if self.running:
			raise DriverAlreadyRunningError("Cannot set file: GDB already running.")
		self.process.stdin.write('-file-exec-and-symbols ' + file + '\n')

	def listen(self, queue):
		while True:
			ln = self.process.stdout.readline()
			if not ln:
				queue.append(('handle_eof', []))
				break
			queue.append(('handle_communication', [ln]))
		self.process = None

	def add_breakpoint(self, id, file, line):
		self.on_log.signal("Adding breakpoint: " + file + ":" + str(line) + "\n")
		cmd = '-break-insert ' + file + ':' + str(line) + '\n'
		self.process.stdin.write(cmd)

	def remove_breakpoint(self, id):
		asdf = self.doesntexist

class BreakpointCollection(object):
	def __init__(self):
		self.bps = {}
		self.on_add = Delegate()
		self.on_remove = Delegate()

	def add(self, id, file, line):
		if id in self.bps:
			raise BreakpointAlreadyExistsError(
					"Cannot add breakpoint " + id + " - id already in use.")
		self.bps[id] = (file, line)
		self.on_add.signal(id, file, line)

	def remove(self, id):
		try:
			file, line = self.bps[i]
			del self.bps[i]
		except KeyError:
			raise BreakpointMissingError(
					"Cannot remove breakpoint " + id + " - no such breakpoint.")
		self.on_remove.signal(id, file, line)

class LogWindow(object):
	def __init__(self, session_id):
		self.buffer = None
		self.session_id = session_id

	def create_buffer(self):
		buf_name = "/DbgLog" + str(self.session_id)
		cmd = "bad " + buf_name
		vim.command(cmd)
		cmd = 'call setbufvar("' + buf_name + '", "&buftype", "nofile")'
		vim.command(cmd)
		bufs = [b for b in vim.buffers if b.name == buf_name]
		try:
			self.buffer = bufs[0]
		except IndexError:
			raise CreateBufferError("Error while creating log buffer.")

	def display(self):
		if not self.buffer:
			raise BufferMissingError("Cannot display log window - buffer not created.")
		existing_winds = [w for w in vim.windows if w.buffer == self.buffer]
		if not existing_winds:
			cmd = "sb " + self.buffer.name
			vim.command(cmd)

	def log_message(self, msg):
		if not self.buffer:
			raise BufferMissingError("Cannot display log message - buffer not created.")
		self.buffer.append(msg)
		for w in (w for w in vim.windows if w.buffer == self.buffer):
			w.cursor = len(self.buffer), 1
