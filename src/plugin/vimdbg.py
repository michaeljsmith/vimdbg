import vim
import subprocess
import threading

def log(msg):
	f = file('log', 'a+')
	try:
		f.write(msg)
	finally:
		f.close()

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

class Delegate(object):
	def __init__(self):
		self.hndlrs = {}

	def add_handler(self, id, hndlr):
		self.hndlrs[id] = hndlr

	def remove_handler(self, id, hndlr):
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
	def __init__(self, driver):
		self.session_id = get_session_id()
		self.driver = driver
		self.driver_proxy = DriverProxy(driver)
		self.log_window = LogWindow(self.session_id)
		self.thread = None
		self.message_queue = ThreadMessageQueue()

		# Display all communications in the log window.
		self.driver_proxy.on_communication.add_handler(
				self.log_window, self.log_window.log_message)

	def display_log_window(self):
		self.log_window.create_buffer()
		self.log_window.display()

	def start_debugger(self):
		log("start_debugger\n")
		self.log_window.log_message("Starting debugger.")
		if self.thread:
			raise ThreadAlreadyRunningError(
					'Cannot start listen thread - already running.')

		self.driver.start()

		driver = self.driver
		message_queue = self.message_queue
		class Thread(threading.Thread):
			def run(self):
				driver.listen(message_queue)
		self.thread = Thread()
		self.thread.start()

	def stop_debugger(self):
		self.log_window.log_message("Stopping debugger.")
		log("stop_debugger\n")
		if not self.thread:
			raise ThreadNotRunningError(
					'Cannot stop debugger - listen thread not running.')
		log("calling driver.stop\n")
		self.driver.stop()
		log("calling thread.join\n")
		self.thread.join()
		log("calling driver.read_all_pending\n")
		self.driver_proxy.read_all_pending(self.message_queue)
		log("stop_debugger returning\n")

	def shutdown(self):
		log("shutdown\n")
		try:
			log("calling stop_debugger\n")
			self.stop_debugger()
		except DebuggerMissingError: pass

	def update(self):
		log("update\n")
		if not self.thread:
			raise ThreadNotRunningError(
					'Cannot update dbg thread - listen thread not running.')
		self.driver_proxy.read_all_pending(self.message_queue)

class DriverProxy(object):
	def __init__(self, driver):
		self.driver = driver
		self.on_communication = Delegate()
	
	def read(self, queue):
		try:
			msg = queue.pop()
			log("driver_proxy: msg recv: " + str(msg) + "\n")
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
		log("driver_proxy.read_all_pending()\n")
		log("queue = " + str(queue.items))
		while not queue.empty():
			self.read(queue)

	def handle_communication(self, msg):
		self.on_communication.signal(msg)

	def handle_eof(self):
		print "Debugger process exitted."

class GdbDriver(object):
	def __init__(self):
		self.process = None

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
		log('driver.stop\n')
		if not self.process:
			raise DebuggerMissingError("Cannot stop debugger: GDB not running.")
		self.process.stdin.close()
		log('driver.stop - waiting\n')
		self.process.wait()
		log('driver.stop - returning\n')

	def listen(self, queue):
		log('Listen thread starting to listen.\n')
		while True:
			ln = self.process.stdout.readline()
			log('Listen thread: received line: ' + ln)
			if not ln:
				queue.append(('handle_eof', []))
				break
			else:
				queue.append(('handle_communication', [ln]))
		log('Listen thread ending.\n')
		self.process = None

class BreakpointCollection(object):
	pass

class BreakpointWindow(object):
	pass

class WatchList(object):
	pass

class WatchWindow(object):
	pass

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

