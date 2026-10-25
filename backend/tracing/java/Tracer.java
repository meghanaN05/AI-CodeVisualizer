import com.sun.jdi.AbsentInformationException;
import com.sun.jdi.ArrayReference;
import com.sun.jdi.BooleanValue;
import com.sun.jdi.Bootstrap;
import com.sun.jdi.ByteValue;
import com.sun.jdi.CharValue;
import com.sun.jdi.ClassType;
import com.sun.jdi.DoubleValue;
import com.sun.jdi.Field;
import com.sun.jdi.FloatValue;
import com.sun.jdi.IntegerValue;
import com.sun.jdi.LocalVariable;
import com.sun.jdi.Location;
import com.sun.jdi.LongValue;
import com.sun.jdi.Method;
import com.sun.jdi.ObjectReference;
import com.sun.jdi.PrimitiveValue;
import com.sun.jdi.ReferenceType;
import com.sun.jdi.ShortValue;
import com.sun.jdi.StackFrame;
import com.sun.jdi.StringReference;
import com.sun.jdi.ThreadReference;
import com.sun.jdi.VMDisconnectedException;
import com.sun.jdi.Value;
import com.sun.jdi.VirtualMachine;
import com.sun.jdi.VoidValue;
import com.sun.jdi.connect.Connector;
import com.sun.jdi.connect.LaunchingConnector;
import com.sun.jdi.event.BreakpointEvent;
import com.sun.jdi.event.ClassPrepareEvent;
import com.sun.jdi.event.Event;
import com.sun.jdi.event.EventSet;
import com.sun.jdi.event.ExceptionEvent;
import com.sun.jdi.event.MethodExitEvent;
import com.sun.jdi.event.VMDeathEvent;
import com.sun.jdi.event.VMDisconnectEvent;
import com.sun.jdi.event.VMStartEvent;
import com.sun.jdi.request.BreakpointRequest;
import com.sun.jdi.request.ClassPrepareRequest;
import com.sun.jdi.request.EventRequest;
import com.sun.jdi.request.EventRequestManager;
import com.sun.jdi.request.ExceptionRequest;
import com.sun.jdi.request.MethodExitRequest;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintStream;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

/**
 * Compile a Java snippet and trace it with the Java Debug Interface.
 *
 * Usage: Tracer <srcFile> <classesDir> <mainClass|-> <maxSteps> <deadlineMs> <bootDir>
 *
 * Prints one JSON trace (format: backend/tracing/__init__.py) on stdout.
 * Semantics mirror python_runner.py: a "line" step before each line runs,
 * "call" at method entry (locals = parameters), "return" with return_value,
 * user frames only, heap objects keyed by a stable per-object id.
 */
public final class Tracer {
    static final int MAX_ITEMS = 64;
    static final int MAX_DEPTH = 12;
    static final String DRIVER_CLASS = "__TraceDriver";
    static final String BOOT_CLASS = "TraceBoot";
    static final String[] EXCLUDES = {
        "java.*", "javax.*", "jdk.*", "sun.*", "com.sun.*", BOOT_CLASS + "*", DRIVER_CLASS,
    };

    static final class StopTracing extends RuntimeException {
        StopTracing() {
            super(null, null, false, false);
        }
    }

    final Path classesDir;
    final String mainClass;
    final int maxSteps;
    final long deadlineMs;
    final String bootDir;

    final Set<String> userClasses = new HashSet<>();
    final List<ReferenceType> preparedUserTypes = new ArrayList<>();
    final List<Object> steps = new ArrayList<>();
    final Map<Long, String> ids = new HashMap<>();
    final Map<Long, Object> immutableCache = new HashMap<>();
    final Map<Integer, Integer> lastLine = new HashMap<>();
    final Map<Integer, Long> lastIndex = new HashMap<>();
    EventRequestManager erm;

    String error = null;
    boolean truncated = false;
    VirtualMachine vm;
    ThreadReference mainThread;
    ReferenceType bootType;
    ObjectReference outRef;
    int outBytesRead = 0;
    final ByteArrayOutputStream outBytes = new ByteArrayOutputStream();
    int stdoutCharsReported = 0;
    final StringBuilder debuggeeStderr = new StringBuilder();

    Tracer(Path classesDir, String mainClass, int maxSteps, long deadlineMs, String bootDir) {
        this.classesDir = classesDir;
        this.mainClass = mainClass;
        this.maxSteps = maxSteps;
        this.deadlineMs = deadlineMs;
        this.bootDir = bootDir;
    }

    public static void main(String[] args) throws Exception {
        PrintStream out = new PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), true, "UTF-8");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("language", "java");
        Path src = Paths.get(args[0]);
        Path classes = Paths.get(args[1]);
        Tracer tracer = new Tracer(classes, args[2], Integer.parseInt(args[3]), Long.parseLong(args[4]), args[5]);
        result.put("steps", tracer.steps);

        String compileError = compile(src, classes);
        if (compileError != null) {
            result.put("error", compileError);
            result.put("truncated", false);
            result.put("stdout", "");
            out.print(Json.write(result));
            out.flush();
            System.exit(0);
        }
        if ("-".equals(tracer.mainClass)) {
            result.put("error", "Nothing to run: add a main method, or a method we can call with example input");
            result.put("truncated", false);
            result.put("stdout", "");
            out.print(Json.write(result));
            out.flush();
            System.exit(0);
        }

        try {
            tracer.run();
        } catch (VMDisconnectedException ignored) {
            // the program ended
        } catch (Throwable t) {
            if (tracer.error == null) {
                tracer.error = "Tracer failed: " + t;
            }
        } finally {
            tracer.shutdown();
        }
        String stdout = tracer.allStdout();
        result.put("error", tracer.error);
        result.put("truncated", tracer.truncated);
        result.put("stdout", stdout.length() > 4000 ? stdout.substring(stdout.length() - 4000) : stdout);
        out.print(Json.write(result));
        out.flush();
        System.exit(0);
    }

    // ------------------------------------------------------------- compile

    static String compile(Path src, Path classes) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            return "Java compiler not available on the server (a JDK is required)";
        }
        Files.createDirectories(classes);
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager files =
                 compiler.getStandardFileManager(diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {
            List<String> options = Arrays.asList(
                "-g", "-d", classes.toString(), "-proc:none", "-nowarn", "-Xlint:none",
                "-encoding", "UTF-8", "-implicit:none", "-cp", classes.toString());
            Boolean ok = compiler.getTask(new StringWriter(), files, diagnostics, options, null,
                files.getJavaFileObjects(src.toFile())).call();
            if (Boolean.TRUE.equals(ok)) {
                return null;
            }
        }
        for (Diagnostic<? extends JavaFileObject> d : diagnostics.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                String message = d.getMessage(Locale.ROOT).split("\n")[0];
                return "Compile error: " + message + " (line " + d.getLineNumber() + ")";
            }
        }
        return "Compile error";
    }

    // ----------------------------------------------------------------- run

    void run() throws Exception {
        try (Stream<Path> walk = Files.walk(classesDir)) {
            for (Path p : walk.collect(Collectors.toList())) {
                String rel = classesDir.relativize(p).toString();
                if (rel.endsWith(".class")) {
                    String name = rel.substring(0, rel.length() - 6).replace(File.separatorChar, '.');
                    if (!name.equals(DRIVER_CLASS)) {
                        userClasses.add(name);
                    }
                }
            }
        }

        LaunchingConnector connector = Bootstrap.virtualMachineManager().defaultConnector();
        Map<String, Connector.Argument> arguments = connector.defaultArguments();
        long watchdogMs = deadlineMs + 5000;
        // TraceBoot preloads the user classes so none is first loaded inside
        // a snapshot() invocation (its ClassPrepare would suspend the thread).
        arguments.get("main").setValue(BOOT_CLASS + " " + mainClass + " " + watchdogMs + " " + String.join(" ", userClasses));
        arguments.get("options").setValue(
            "-cp " + bootDir + File.pathSeparator + classesDir
                + " -Xmx256m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:-UsePerfData"
                + " -Xshare:auto -Djava.awt.headless=true -Dfile.encoding=UTF-8");
        Connector.Argument home = arguments.get("home");
        if (home != null) {
            home.setValue(System.getProperty("java.home"));
        }
        long start = System.currentTimeMillis();
        vm = connector.launch(arguments);
        Process process = vm.process();
        // If a JDWP call ever blocks past the deadline, kill the debuggee:
        // that fails the pending call and the loop below reports the timeout.
        Thread killer = new Thread(() -> {
            try {
                Thread.sleep(deadlineMs + 2000);
            } catch (InterruptedException e) {
                return;
            }
            if (error == null) {
                error = "Execution timed out after " + (deadlineMs / 1000) + "s";
            }
            process.destroyForcibly();
        }, "tracer-deadline");
        killer.setDaemon(true);
        killer.start();
        process.getOutputStream().close();
        drain(process.getInputStream(), null);
        drain(process.getErrorStream(), debuggeeStderr);

        erm = vm.eventRequestManager();
        ClassPrepareRequest prepare = erm.createClassPrepareRequest();
        for (String ex : EXCLUDES) {
            prepare.addClassExclusionFilter(ex);
        }
        prepare.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
        prepare.enable();
        ClassPrepareRequest prepareBoot = erm.createClassPrepareRequest();
        prepareBoot.addClassFilter(BOOT_CLASS);
        prepareBoot.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
        prepareBoot.enable();

        boolean finished = false;
        while (!finished) {
            long remaining = start + deadlineMs - System.currentTimeMillis();
            if (remaining <= 0) {
                error = "Execution timed out after " + (deadlineMs / 1000) + "s";
                break;
            }
            EventSet set = vm.eventQueue().remove(remaining);
            if (set == null) {
                continue;
            }
            try {
                for (Event e : set) {
                    if (e instanceof VMStartEvent) {
                        mainThread = ((VMStartEvent) e).thread();
                        // Only exceptions thrown in user code: JDK and TraceBoot are
                        // excluded, so none can fire inside a snapshot() invocation.
                        ExceptionRequest thrown = erm.createExceptionRequest(null, true, true);
                        for (String ex : EXCLUDES) {
                            thrown.addClassExclusionFilter(ex);
                        }
                        thrown.addThreadFilter(mainThread);
                        thrown.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                        thrown.enable();
                    } else if (e instanceof ExceptionEvent) {
                        onException((ExceptionEvent) e);
                    } else if (e instanceof ClassPrepareEvent) {
                        onClassPrepare(erm, ((ClassPrepareEvent) e).referenceType());
                    } else if (e instanceof MethodExitEvent) {
                        onExit((MethodExitEvent) e);
                    } else if (e instanceof BreakpointEvent) {
                        BreakpointEvent bp = (BreakpointEvent) e;
                        if (bp.location().declaringType().name().equals(BOOT_CLASS)) {
                            onDone();
                            finished = true;
                        } else {
                            onBreakpoint(bp);
                        }
                    } else if (e instanceof VMDeathEvent || e instanceof VMDisconnectEvent) {
                        finished = true;
                    }
                }
            } catch (StopTracing stop) {
                truncated = true;
                break;
            }
            if (!finished) {
                set.resume();
            }
        }
    }

    static final int LINE = 1;
    static final int ENTRY = 2;
    static final int RETURN = 4;
    final Map<Location, Integer> breakpointKinds = new HashMap<>();
    final Map<ReferenceType, MethodExitRequest> exitRequests = new HashMap<>();
    MethodExitRequest armedExit;

    /**
     * Everything is driven by breakpoints in user code, never by global
     * method-entry/exit or single-step events: those put the thread in
     * interpreter-only mode and make the agent filter every JDK call.
     *
     * - ENTRY: a method's first bytecode ("call" step).
     * - LINE: every line-table entry, plus the target of each backward branch
     *   whose loop has no other entry for that line. javac merges same-line
     *   statements into one entry, so without the latter a one-line loop
     *   (`for (...) s += a[i];`) would produce a single step, while Python
     *   reports every iteration (a backward jump is a new line event).
     * - RETURN: each return instruction; it arms a class-filtered
     *   MethodExitRequest for just that exit, to read the return value.
     */
    void installBreakpoints(ReferenceType type) {
        for (Method m : type.methods()) {
            if (m.isAbstract() || m.isNative() || !isTraceable(m)) {
                continue;
            }
            List<Location> lines;
            try {
                lines = m.allLineLocations();
            } catch (AbsentInformationException e) {
                continue;
            }
            if (lines.isEmpty()) {
                continue;
            }
            Map<Long, Integer> kinds = new java.util.TreeMap<>();
            for (Location l : lines) {
                kinds.merge(l.codeIndex(), LINE, (a, b) -> a | b);
            }
            kinds.merge(m.location().codeIndex(), ENTRY, (a, b) -> a | b);
            List<Long> returns = new ArrayList<>();
            for (long[] jump : scanBytecode(m.bytecodes(), returns)) {
                long target = jump[0];
                long source = jump[1];
                Location t = m.locationOfCodeIndex(target);
                if (t == null || (kinds.getOrDefault(target, 0) & LINE) != 0) {
                    continue;
                }
                boolean covered = false;
                for (Location l : lines) {
                    if (l.codeIndex() > target && l.codeIndex() <= source && l.lineNumber() == t.lineNumber()) {
                        covered = true;
                    }
                }
                if (!covered) {
                    kinds.merge(target, LINE, (a, b) -> a | b);
                }
            }
            for (long index : returns) {
                kinds.merge(index, RETURN, (a, b) -> a | b);
            }
            for (Map.Entry<Long, Integer> k : kinds.entrySet()) {
                Location l = m.locationOfCodeIndex(k.getKey());
                if (l == null) {
                    continue;
                }
                breakpointKinds.put(l, k.getValue());
                BreakpointRequest bp = erm.createBreakpointRequest(l);
                bp.addThreadFilter(mainThread);
                bp.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                bp.enable();
            }
        }
    }

    /** (target, source) of every backward branch; return-instruction offsets go to `returns`. */
    static List<long[]> scanBytecode(byte[] code, List<Long> returns) {
        List<long[]> jumps = new ArrayList<>();
        int pc = 0;
        try {
            while (pc < code.length) {
                int op = code[pc] & 0xff;
                int length;
                if ((op >= 0x99 && op <= 0xa8) || op == 0xc6 || op == 0xc7) {
                    int offset = (short) (((code[pc + 1] & 0xff) << 8) | (code[pc + 2] & 0xff));
                    if (offset < 0) {
                        jumps.add(new long[] {pc + offset, pc});
                    }
                    length = 3;
                } else if (op == 0xc8 || op == 0xc9) {
                    int offset = ((code[pc + 1] & 0xff) << 24) | ((code[pc + 2] & 0xff) << 16)
                        | ((code[pc + 3] & 0xff) << 8) | (code[pc + 4] & 0xff);
                    if (offset < 0) {
                        jumps.add(new long[] {pc + offset, pc});
                    }
                    length = 5;
                } else if (op == 0xaa || op == 0xab) {
                    int base = (pc + 4) & ~3; // skip padding after the opcode
                    if (op == 0xaa) {
                        int low = readInt(code, base + 4);
                        int high = readInt(code, base + 8);
                        length = base - pc + 12 + (high - low + 1) * 4;
                    } else {
                        int pairs = readInt(code, base + 4);
                        length = base - pc + 8 + pairs * 8;
                    }
                } else if (op >= 0xac && op <= 0xb1) {
                    returns.add((long) pc);
                    length = 1;
                } else if (op == 0xc4) {
                    length = (code[pc + 1] & 0xff) == 0x84 ? 6 : 4;
                } else {
                    length = OPCODE_LENGTH[op];
                }
                if (length <= 0) {
                    return jumps; // unknown opcode: keep what we found
                }
                pc += length;
            }
        } catch (ArrayIndexOutOfBoundsException e) {
            // truncated/odd bytecode: keep what we found
        }
        return jumps;
    }

    static int readInt(byte[] code, int at) {
        return ((code[at] & 0xff) << 24) | ((code[at + 1] & 0xff) << 16) | ((code[at + 2] & 0xff) << 8) | (code[at + 3] & 0xff);
    }

    static final int[] OPCODE_LENGTH = new int[256];
    static {
        Arrays.fill(OPCODE_LENGTH, 0);
        for (int op = 0x00; op <= 0xc9; op++) {
            OPCODE_LENGTH[op] = 1;
        }
        OPCODE_LENGTH[0x10] = 2; // bipush
        OPCODE_LENGTH[0x11] = 3; // sipush
        OPCODE_LENGTH[0x12] = 2; // ldc
        OPCODE_LENGTH[0x13] = 3;
        OPCODE_LENGTH[0x14] = 3;
        for (int op = 0x15; op <= 0x19; op++) {
            OPCODE_LENGTH[op] = 2; // loads with index
        }
        for (int op = 0x36; op <= 0x3a; op++) {
            OPCODE_LENGTH[op] = 2; // stores with index
        }
        OPCODE_LENGTH[0x84] = 3; // iinc
        OPCODE_LENGTH[0xa9] = 2; // ret
        for (int op = 0xb2; op <= 0xb8; op++) {
            OPCODE_LENGTH[op] = 3; // field access, invokes
        }
        OPCODE_LENGTH[0xb9] = 5; // invokeinterface
        OPCODE_LENGTH[0xba] = 5; // invokedynamic
        OPCODE_LENGTH[0xbb] = 3; // new
        OPCODE_LENGTH[0xbc] = 2; // newarray
        OPCODE_LENGTH[0xbd] = 3; // anewarray
        OPCODE_LENGTH[0xc0] = 3; // checkcast
        OPCODE_LENGTH[0xc1] = 3; // instanceof
        OPCODE_LENGTH[0xc5] = 4; // multianewarray
    }

    void onClassPrepare(EventRequestManager erm, ReferenceType type) {
        if (type.name().equals(BOOT_CLASS)) {
            bootType = type;
            Method done = type.methodsByName("done").get(0);
            BreakpointRequest bp = erm.createBreakpointRequest(done.location());
            bp.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            bp.enable();
        } else if (userClasses.contains(type.name())) {
            preparedUserTypes.add(type);
            installBreakpoints(type);
        }
    }

    void onDone() {
        readStdout();
        try {
            Value err = bootType.getValue(bootType.fieldByName("ERROR"));
            if (err instanceof StringReference) {
                error = ((StringReference) err).value();
            }
        } catch (RuntimeException ignored) {
            // keep whatever we have
        }
    }

    // -------------------------------------------------------------- events

    boolean isUser(ReferenceType type) {
        return userClasses.contains(type.name());
    }

    boolean isUserFrame(Location location) {
        return isUser(location.declaringType()) && isTraceable(location.method());
    }

    /** User methods worth showing: not class initializers or compiler bridges. */
    static boolean isTraceable(Method m) {
        if (m.name().equals("<clinit>") || m.isBridge()) {
            return false;
        }
        if (m.isConstructor() && m.declaringType() instanceof ClassType && ((ClassType) m.declaringType()).isEnum()) {
            return false; // enum constants are built by the class initializer
        }
        return !m.isSynthetic() || m.name().startsWith("lambda$");
    }

    List<StackFrame> userFrames(ThreadReference thread) throws Exception {
        List<StackFrame> frames = new ArrayList<>();
        for (StackFrame frame : thread.frames()) {
            if (isUserFrame(frame.location())) {
                frames.add(frame);
            }
        }
        java.util.Collections.reverse(frames);
        return frames;
    }

    static boolean isMainMethod(Method m) {
        return m.name().equals("main") && m.isStatic() && m.signature().equals("([Ljava/lang/String;)V");
    }

    final Map<Integer, Method> frameMethod = new HashMap<>();

    void forgetBelow(int depth) {
        lastLine.keySet().removeIf(d -> d > depth);
        lastIndex.keySet().removeIf(d -> d > depth);
        frameMethod.keySet().removeIf(d -> d > depth);
    }

    void forget(int depth) {
        lastLine.remove(depth);
        lastIndex.remove(depth);
        frameMethod.remove(depth);
    }

    void onBreakpoint(BreakpointEvent e) throws Exception {
        Location location = e.location();
        Integer kind = breakpointKinds.get(location);
        if (kind == null || !e.thread().equals(mainThread) || !isUserFrame(location)) {
            return;
        }
        Method method = location.method();
        List<StackFrame> frames = userFrames(e.thread());
        int depth = frames.size();
        forgetBelow(depth); // frames deeper than this one have ended (maybe by an exception)
        boolean programEntry = depth == 1 && isMainMethod(method);

        // A method's first bytecode is a call, unless this frame looped back to it.
        if ((kind & ENTRY) != 0 && !(method.equals(frameMethod.get(depth)) && lastIndex.containsKey(depth))) {
            forget(depth);
            frameMethod.put(depth, method);
            if (!programEntry) {
                snapshot(e.thread(), frames, "call", location, null, false);
            }
        }
        frameMethod.put(depth, method);

        if ((kind & LINE) != 0 && location.lineNumber() >= 0) {
            Integer line = lastLine.get(depth);
            Long index = lastIndex.get(depth);
            lastLine.put(depth, location.lineNumber());
            lastIndex.put(depth, location.codeIndex());
            // Like Python: a new line, or a backward jump (next loop iteration).
            // Coming back mid-line after a call returns is neither.
            boolean sameLineForward = line != null && line == location.lineNumber() && location.codeIndex() > index;
            if (!sameLineForward) {
                // the "call" snapshot's invocation invalidated earlier StackFrames
                snapshot(e.thread(), userFrames(e.thread()), "line", location, null, false);
            }
        }

        if ((kind & RETURN) != 0 && !programEntry) {
            MethodExitRequest exit = exitRequests.get(location.declaringType());
            if (exit == null) {
                exit = erm.createMethodExitRequest();
                exit.addClassFilter(location.declaringType());
                exit.addThreadFilter(mainThread);
                exit.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                exitRequests.put(location.declaringType(), exit);
            }
            exit.enable();
            armedExit = exit;
        }
    }

    /** Like Python's tracer: a "return" (value null) for each frame the exception unwinds. */
    void onException(ExceptionEvent e) throws Exception {
        ThreadReference thread = e.thread();
        if (!thread.equals(mainThread)) {
            return;
        }
        List<StackFrame> all = thread.frames();
        Location catchAt = e.catchLocation();
        int catchIndex = all.size();
        if (catchAt != null) {
            for (int i = 0; i < all.size(); i++) {
                if (all.get(i).location().method().equals(catchAt.method())) {
                    catchIndex = i;
                    break;
                }
            }
        }
        int popped = 0;
        for (int i = 0; i < catchIndex; i++) {
            if (isUserFrame(all.get(i).location())) {
                popped++;
            }
        }
        int depth = userFrames(thread).size();
        for (int k = 0; k < popped; k++) {
            List<StackFrame> frames = userFrames(thread); // refreshed: snapshots invalidate frames
            int d = depth - k;
            List<StackFrame> live = frames.subList(0, d);
            if (d == 1 && isMainMethod(live.get(0).location().method())) {
                break; // the program's entry point, like Python's <module>
            }
            snapshot(thread, live, "return", live.get(d - 1).location(), null, true);
            forget(d);
        }
    }

    void onExit(MethodExitEvent e) throws Exception {
        if (armedExit != null) {
            armedExit.disable();
            armedExit = null;
        }
        if (!e.thread().equals(mainThread) || !isUserFrame(e.location())) {
            return;
        }
        List<StackFrame> frames = userFrames(e.thread());
        snapshot(e.thread(), frames, "return", e.location(), e.returnValue(), true);
        forget(frames.size());
    }

    // ------------------------------------------------------------ snapshot

    /** A value the debuggee-side encoder will fill in. */
    static final class Pending {
        final int index;

        Pending(int index) {
            this.index = index;
        }
    }

    /** Pre-encoded JSON spliced into the output as-is. */
    static final class Raw {
        final String json;

        Raw(String json) {
            this.json = json;
        }
    }

    boolean remoteEncoding = !Boolean.getBoolean("tracer.localEncoding"); // debug switch for the fallback
    ClassType bootClass;
    ArrayReference rootsArray;
    Method snapshotMethod;
    static final int MAX_ROOTS = 512;

    void snapshot(ThreadReference thread, List<StackFrame> frames, String event, Location location,
                  Value returnValue, boolean isReturn) throws Exception {
        if (steps.size() >= maxSteps) {
            throw new StopTracing();
        }
        Encoder local = new Encoder();
        List<ObjectReference> roots = new ArrayList<>();
        List<Object[]> slots = new ArrayList<>(); // {map, key, Pending}
        List<Object> stack = new ArrayList<>();

        Map<String, Object> statics = new LinkedHashMap<>();
        for (Map.Entry<String, Value> e : staticValues().entrySet()) {
            put(statics, e.getKey(), e.getValue(), local, roots, slots);
        }
        if (!statics.isEmpty()) {
            stack.add(frame("<static>", statics));
        }
        String func = "<static>";
        for (StackFrame f : frames) {
            Method m = f.location().method();
            Map<String, Object> locals = new LinkedHashMap<>();
            if (!m.isStatic() && !m.isNative()) {
                ObjectReference self = f.thisObject();
                if (self != null) {
                    put(locals, "this", self, local, roots, slots);
                }
            }
            try {
                List<LocalVariable> vars = f.visibleVariables();
                Map<LocalVariable, Value> values = f.getValues(vars);
                for (LocalVariable var : vars) {
                    put(locals, var.name(), values.get(var), local, roots, slots);
                }
            } catch (AbsentInformationException absent) {
                List<Value> args = f.getArgumentValues();
                for (int i = 0; i < args.size(); i++) {
                    put(locals, "arg" + i, args.get(i), local, roots, slots);
                }
            }
            func = funcName(m);
            stack.add(frame(func, locals));
        }

        Map<String, Object> step = new LinkedHashMap<>();
        step.put("line", location.lineNumber());
        step.put("event", event);
        step.put("func", func);
        step.put("stack", stack);
        step.put("heap", local.heap);
        if (isReturn) {
            put(step, "return_value", returnValue, local, roots, slots);
        }

        if (!roots.isEmpty()) {
            String[] encoded = null;
            try {
                encoded = remoteSnapshot(thread, roots);
            } catch (Exception failed) {
                remoteEncoding = false; // fall back to reading fields over JDI from now on
            }
            if (encoded != null) {
                step.put("heap", new Raw(encoded[0]));
                for (Object[] slot : slots) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> target = (Map<String, Object>) slot[0];
                    target.put((String) slot[1], new Raw(encoded[1 + ((Pending) slot[2]).index]));
                }
            } else {
                for (Object[] slot : slots) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> target = (Map<String, Object>) slot[0];
                    target.put((String) slot[1], local.encode(roots.get(((Pending) slot[2]).index), 0));
                }
            }
        }
        String printed = readStdout();
        if (!printed.isEmpty()) {
            step.put("stdout", printed);
        }
        steps.add(step);
    }

    /** Encode scalars here; queue objects for the debuggee-side encoder. */
    void put(Map<String, Object> target, String key, Value v, Encoder local,
             List<ObjectReference> roots, List<Object[]> slots) {
        if (!remoteEncoding || !(v instanceof ObjectReference) || v instanceof StringReference) {
            target.put(key, local.encode(v, 0));
            return;
        }
        if (roots.size() >= MAX_ROOTS) {
            target.put(key, "…");
            return;
        }
        roots.add((ObjectReference) v);
        Pending pending = new Pending(roots.size() - 1);
        target.put(key, pending);
        slots.add(new Object[] {target, key, pending});
    }

    /** [heap JSON, root 0 JSON, root 1 JSON, ...] from one TraceBoot.snapshot() call. */
    String[] remoteSnapshot(ThreadReference thread, List<ObjectReference> roots) throws Exception {
        if (snapshotMethod == null) {
            bootClass = (ClassType) bootType;
            snapshotMethod = bootClass.methodsByName("snapshot").get(0);
            rootsArray = (ArrayReference) bootClass.getValue(bootClass.fieldByName("ROOTS"));
        }
        rootsArray.setValues(0, roots, 0, roots.size());
        Value result = bootClass.invokeMethod(thread, snapshotMethod,
            java.util.Collections.singletonList(vm.mirrorOf(roots.size())), ClassType.INVOKE_SINGLE_THREADED);
        String text = ((StringReference) result).value();
        int split = text.indexOf('\u0000');
        String[] values = text.substring(split + 1).split("\u0001", -1);
        if (split < 0 || values.length != roots.size()) {
            throw new IllegalStateException("bad snapshot");
        }
        String[] out = new String[values.length + 1];
        out[0] = text.substring(0, split);
        System.arraycopy(values, 0, out, 1, values.length);
        return out;
    }

    static Map<String, Object> frame(String func, Map<String, Object> locals) {
        Map<String, Object> frame = new LinkedHashMap<>();
        frame.put("func", func);
        frame.put("locals", locals);
        return frame;
    }

    static String funcName(Method m) {
        String name = m.name();
        if (name.equals("<init>")) {
            return "__init__"; // constructors, like Python's __init__
        }
        if (name.startsWith("lambda$")) {
            return "<lambda>";
        }
        return name;
    }

    Map<String, Value> staticValues() {
        Map<String, Value> statics = new LinkedHashMap<>();
        for (ReferenceType type : preparedUserTypes) {
            List<Field> fields = new ArrayList<>();
            for (Field f : type.fields()) {
                String n = f.name();
                if (f.isStatic() && !f.isSynthetic() && !f.isEnumConstant()
                    && !n.equals("serialVersionUID") && !n.startsWith("$") && !statics.containsKey(n)) {
                    fields.add(f);
                }
            }
            if (fields.isEmpty()) {
                continue;
            }
            Map<Field, Value> values = type.getValues(fields);
            for (Field f : fields) {
                statics.put(f.name(), values.get(f));
            }
        }
        return statics;
    }

    String readStdout() {
        try {
            if (outRef == null) {
                if (bootType == null) {
                    return "";
                }
                Value v = bootType.getValue(bootType.fieldByName("OUT"));
                if (!(v instanceof ObjectReference)) {
                    return "";
                }
                outRef = (ObjectReference) v;
            }
            ReferenceType t = outRef.referenceType();
            Field countField = t.fieldByName("count");
            Field bufField = t.fieldByName("buf");
            Map<Field, Value> values = outRef.getValues(Arrays.asList(countField, bufField));
            int count = ((IntegerValue) values.get(countField)).value();
            if (count > outBytesRead) {
                ArrayReference buf = (ArrayReference) values.get(bufField);
                List<Value> bytes = buf.getValues(outBytesRead, count - outBytesRead);
                for (Value b : bytes) {
                    outBytes.write(((ByteValue) b).value());
                }
                outBytesRead = count;
            }
        } catch (RuntimeException ignored) {
            return "";
        }
        String all = allStdout();
        String delta = all.substring(Math.min(stdoutCharsReported, all.length()));
        stdoutCharsReported = all.length();
        return delta;
    }

    String allStdout() {
        return new String(outBytes.toByteArray(), StandardCharsets.UTF_8);
    }

    void shutdown() {
        if (vm != null) {
            Process p = null;
            try {
                p = vm.process();
            } catch (RuntimeException ignored) {
                // already gone
            }
            try {
                vm.exit(0);
            } catch (RuntimeException ignored) {
                // already gone
            }
            if (p != null) {
                p.destroyForcibly();
            }
        }
    }

    static void drain(InputStream in, StringBuilder sink) {
        Thread t = new Thread(() -> {
            byte[] buf = new byte[8192];
            try {
                int n;
                while ((n = in.read(buf)) > 0) {
                    if (sink != null && sink.length() < 8000) {
                        synchronized (sink) {
                            sink.append(new String(buf, 0, n, StandardCharsets.UTF_8));
                        }
                    }
                }
            } catch (IOException ignored) {
                // process ended
            }
        });
        t.setDaemon(true);
        t.start();
    }

    // ------------------------------------------------------------- encoder

    static String simpleName(String typeName) {
        String n = typeName;
        int slash = n.indexOf('/');
        if (n.contains("$$Lambda")) {
            return "lambda";
        }
        if (slash >= 0) {
            n = n.substring(0, slash);
        }
        n = n.substring(n.lastIndexOf('.') + 1);
        return n.substring(n.lastIndexOf('$') + 1);
    }

    static boolean isJdkType(String n) {
        return n.startsWith("java.") || n.startsWith("javax.") || n.startsWith("jdk.")
            || n.startsWith("sun.") || n.startsWith("com.sun.");
    }

    static Object number(double d) {
        if (Double.isNaN(d)) {
            return "NaN";
        }
        if (Double.isInfinite(d)) {
            return d > 0 ? "∞" : "-∞";
        }
        return d;
    }

    static final Object NOT_SCALAR = new Object();

    final class Encoder {
        final Map<String, Object> heap = new LinkedHashMap<>();

        Object encode(Value v, int depth) {
            if (v == null || v instanceof VoidValue) {
                return null;
            }
            if (v instanceof BooleanValue) {
                return ((BooleanValue) v).value();
            }
            if (v instanceof CharValue) {
                return String.valueOf(((CharValue) v).value());
            }
            if (v instanceof FloatValue || v instanceof DoubleValue) {
                return number(((PrimitiveValue) v).doubleValue());
            }
            if (v instanceof PrimitiveValue) {
                return ((PrimitiveValue) v).longValue();
            }
            ObjectReference o = (ObjectReference) v;
            Object scalar = scalarOf(o);
            if (scalar != NOT_SCALAR) {
                return scalar;
            }
            if (depth > MAX_DEPTH) {
                return "…";
            }
            String ref = idOf(o);
            if (!heap.containsKey(ref)) {
                heap.put(ref, new LinkedHashMap<String, Object>()); // reserve so cycles terminate
                heap.put(ref, describe(o, depth));
            }
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("ref", ref);
            return r;
        }

        String idOf(ObjectReference o) {
            long key = o.uniqueID();
            String id = ids.get(key);
            if (id == null) {
                id = String.valueOf(ids.size() + 1);
                ids.put(key, id);
            }
            return id;
        }

        Object scalarOf(ObjectReference o) {
            if (o instanceof StringReference) {
                long key = o.uniqueID();
                Object cached = immutableCache.get(key);
                if (cached == null) {
                    cached = ((StringReference) o).value();
                    immutableCache.put(key, cached);
                }
                return cached;
            }
            ReferenceType t = o.referenceType();
            String n = t.name();
            switch (n) {
                case "java.lang.Integer":
                case "java.lang.Long":
                case "java.lang.Short":
                case "java.lang.Byte":
                case "java.lang.Double":
                case "java.lang.Float":
                case "java.lang.Boolean":
                case "java.lang.Character": {
                    long key = o.uniqueID();
                    Object cached = immutableCache.get(key);
                    if (cached == null) {
                        cached = encode(o.getValue(t.fieldByName("value")), 0);
                        immutableCache.put(key, cached);
                    }
                    return cached;
                }
                case "java.lang.StringBuilder":
                case "java.lang.StringBuffer":
                    return builderText(o);
                default:
                    break;
            }
            if (t instanceof ClassType && ((ClassType) t).isEnum()) {
                ClassType enumBase = (ClassType) t;
                Field name = enumBase.fieldByName("name");
                if (name != null) {
                    Value v = o.getValue(name);
                    if (v instanceof StringReference) {
                        return ((StringReference) v).value();
                    }
                }
            }
            return NOT_SCALAR;
        }

        Object builderText(ObjectReference o) {
            ReferenceType t = o.referenceType();
            Field valueF = t.fieldByName("value");
            Field countF = t.fieldByName("count");
            Field coderF = t.fieldByName("coder");
            int count = ((IntegerValue) o.getValue(countF)).value();
            Value raw = o.getValue(valueF);
            if (!(raw instanceof ArrayReference) || count == 0) {
                return "";
            }
            ArrayReference arr = (ArrayReference) raw;
            int coder = coderF == null ? -1 : ((ByteValue) o.getValue(coderF)).value();
            StringBuilder sb = new StringBuilder();
            if (coder == -1) { // JDK 8: char[]
                for (Value c : arr.getValues(0, count)) {
                    sb.append(((CharValue) c).value());
                }
            } else if (coder == 0) { // LATIN1
                for (Value b : arr.getValues(0, count)) {
                    sb.append((char) (((ByteValue) b).value() & 0xff));
                }
            } else { // UTF16, little-endian on x86/arm
                List<Value> bytes = arr.getValues(0, count * 2);
                for (int i = 0; i < count; i++) {
                    int lo = ((ByteValue) bytes.get(2 * i)).value() & 0xff;
                    int hi = ((ByteValue) bytes.get(2 * i + 1)).value() & 0xff;
                    sb.append((char) ((hi << 8) | lo));
                }
            }
            return sb.toString();
        }

        Value field(ObjectReference o, String name) {
            Field f = o.referenceType().fieldByName(name);
            return f == null ? null : o.getValue(f);
        }

        Map<String, Value> fields(ObjectReference o, String... names) {
            ReferenceType t = o.referenceType();
            List<Field> list = new ArrayList<>();
            for (String n : names) {
                Field f = t.fieldByName(n);
                if (f != null) {
                    list.add(f);
                }
            }
            Map<Field, Value> raw = o.getValues(list);
            Map<String, Value> out = new HashMap<>();
            for (Map.Entry<Field, Value> e : raw.entrySet()) {
                out.put(e.getKey().name(), e.getValue());
            }
            return out;
        }

        int intOf(Value v) {
            return v instanceof PrimitiveValue ? ((PrimitiveValue) v).intValue() : 0;
        }

        Map<String, Object> kind(String kind, String key, Object value) {
            Map<String, Object> obj = new LinkedHashMap<>();
            obj.put("kind", kind);
            obj.put(key, value);
            return obj;
        }

        List<Object> encodeAll(List<Value> values, int depth) {
            List<Object> items = new ArrayList<>();
            for (Value v : values) {
                if (items.size() >= MAX_ITEMS) {
                    break;
                }
                items.add(encode(v, depth + 1));
            }
            return items;
        }

        List<Value> arrayPrefix(Value arr, int size) {
            if (!(arr instanceof ArrayReference) || size <= 0) {
                return new ArrayList<>();
            }
            ArrayReference a = (ArrayReference) arr;
            return a.getValues(0, Math.min(Math.min(size, a.length()), MAX_ITEMS));
        }

        Map<String, Object> describe(ObjectReference o, int depth) {
            if (o instanceof ArrayReference) {
                ArrayReference a = (ArrayReference) o;
                return kind("list", "items", encodeAll(arrayPrefix(a, a.length()), depth));
            }
            String n = o.referenceType().name();
            Map<String, Object> builtin = isJdkType(n) ? describeJdk(o, n, depth) : null;
            if (builtin != null) {
                return builtin;
            }
            Map<String, Object> obj = new LinkedHashMap<>();
            obj.put("kind", "object");
            obj.put("class", simpleName(n));
            Map<String, Object> fieldValues = new LinkedHashMap<>();
            if (!isJdkType(n) && o.referenceType() instanceof ClassType) {
                // Superclass fields first, each class's fields in declaration order.
                Deque<ClassType> chain = new ArrayDeque<>();
                for (ClassType c = (ClassType) o.referenceType(); c != null; c = c.superclass()) {
                    chain.push(c);
                }
                List<Field> declOrder = new ArrayList<>();
                for (ClassType c : chain) {
                    for (Field f : c.fields()) {
                        if (!f.isStatic() && !f.isSynthetic()) {
                            declOrder.add(f);
                        }
                    }
                }
                Map<Field, Value> values = o.getValues(declOrder);
                for (Field f : declOrder) {
                    fieldValues.put(f.name(), encode(values.get(f), depth + 1));
                }
            }
            obj.put("fields", fieldValues);
            return obj;
        }

        Map<String, Object> describeJdk(ObjectReference o, String n, int depth) {
            switch (n) {
                case "java.util.ArrayList": {
                    Map<String, Value> f = fields(o, "elementData", "size");
                    return kind("list", "items", encodeAll(arrayPrefix(f.get("elementData"), intOf(f.get("size"))), depth));
                }
                case "java.util.Vector":
                case "java.util.Stack": {
                    Map<String, Value> f = fields(o, "elementData", "elementCount");
                    return kind("list", "items", encodeAll(arrayPrefix(f.get("elementData"), intOf(f.get("elementCount"))), depth));
                }
                case "java.util.PriorityQueue":
                case "java.util.concurrent.PriorityBlockingQueue": {
                    Map<String, Value> f = fields(o, "queue", "size");
                    return kind("list", "items", encodeAll(arrayPrefix(f.get("queue"), intOf(f.get("size"))), depth));
                }
                case "java.util.Arrays$ArrayList": {
                    Value a = field(o, "a");
                    int len = a instanceof ArrayReference ? ((ArrayReference) a).length() : 0;
                    return kind("list", "items", encodeAll(arrayPrefix(a, len), depth));
                }
                case "java.util.ImmutableCollections$ListN":
                case "java.util.ImmutableCollections$SetN": {
                    Value a = field(o, "elements");
                    int len = a instanceof ArrayReference ? ((ArrayReference) a).length() : 0;
                    List<Value> vals = new ArrayList<>();
                    for (Value v : arrayPrefix(a, len)) {
                        if (v != null) {
                            vals.add(v);
                        }
                    }
                    return kind(n.endsWith("SetN") ? "set" : "list", "items", encodeAll(vals, depth));
                }
                case "java.util.ImmutableCollections$List12":
                case "java.util.ImmutableCollections$Set12": {
                    Map<String, Value> f = fields(o, "e0", "e1");
                    List<Value> vals = new ArrayList<>();
                    for (String k : new String[] {"e0", "e1"}) {
                        Value v = f.get(k);
                        if (v != null && !(v instanceof ObjectReference
                            && ((ObjectReference) v).referenceType().name().equals("java.lang.Object"))) {
                            vals.add(v);
                        }
                    }
                    return kind(n.endsWith("Set12") ? "set" : "list", "items", encodeAll(vals, depth));
                }
                case "java.util.LinkedList": {
                    List<Value> vals = new ArrayList<>();
                    Value node = field(o, "first");
                    while (node instanceof ObjectReference && vals.size() < MAX_ITEMS) {
                        Map<String, Value> f = fields((ObjectReference) node, "item", "next");
                        vals.add(f.get("item"));
                        node = f.get("next");
                    }
                    return kind("list", "items", encodeAll(vals, depth));
                }
                case "java.util.ArrayDeque": {
                    Map<String, Value> f = fields(o, "elements", "head", "tail");
                    List<Value> vals = new ArrayList<>();
                    if (f.get("elements") instanceof ArrayReference) {
                        ArrayReference a = (ArrayReference) f.get("elements");
                        int len = a.length();
                        int head = intOf(f.get("head"));
                        int tail = intOf(f.get("tail"));
                        int size = ((tail - head) % len + len) % len;
                        if (size > 0) {
                            List<Value> all = a.getValues();
                            for (int i = 0; i < size && vals.size() < MAX_ITEMS; i++) {
                                vals.add(all.get((head + i) % len));
                            }
                        }
                    }
                    return kind("list", "items", encodeAll(vals, depth));
                }
                case "java.util.HashMap":
                case "java.util.LinkedHashMap":
                case "java.util.TreeMap":
                case "java.util.ImmutableCollections$MapN":
                case "java.util.ImmutableCollections$Map1": {
                    List<Value[]> entries = mapEntries(o, n);
                    List<Object> out = new ArrayList<>();
                    for (Value[] kv : entries) {
                        List<Object> pair = new ArrayList<>();
                        pair.add(encode(kv[0], depth + 1));
                        pair.add(encode(kv[1], depth + 1));
                        out.add(pair);
                    }
                    return kind("dict", "entries", out);
                }
                case "java.util.HashSet":
                case "java.util.LinkedHashSet":
                case "java.util.TreeSet": {
                    Value backing = field(o, n.equals("java.util.TreeSet") ? "m" : "map");
                    List<Value> keys = new ArrayList<>();
                    if (backing instanceof ObjectReference) {
                        ObjectReference m = (ObjectReference) backing;
                        for (Value[] kv : mapEntries(m, m.referenceType().name())) {
                            keys.add(kv[0]);
                        }
                    }
                    return kind("set", "items", encodeAll(keys, depth));
                }
                case "java.util.HashMap$Node":
                case "java.util.HashMap$TreeNode":
                case "java.util.LinkedHashMap$Entry":
                case "java.util.TreeMap$Entry":
                case "java.util.AbstractMap$SimpleEntry":
                case "java.util.AbstractMap$SimpleImmutableEntry":
                case "java.util.KeyValueHolder": {
                    Map<String, Value> f = fields(o, "key", "value");
                    List<Value> pair = new ArrayList<>();
                    pair.add(f.get("key"));
                    pair.add(f.get("value"));
                    return kind("tuple", "items", encodeAll(pair, depth));
                }
                default:
                    break;
            }
            if (n.startsWith("java.util.Collections$Unmodifiable") || n.startsWith("java.util.Collections$Synchronized")) {
                for (String inner : new String[] {"list", "c", "m", "s"}) {
                    Value v = field(o, inner);
                    if (v instanceof ObjectReference) {
                        return describe((ObjectReference) v, depth);
                    }
                }
            }
            return null;
        }

        /** Key/value pairs of a JDK map, in its iteration order, read from internal fields. */
        List<Value[]> mapEntries(ObjectReference map, String n) {
            List<Value[]> out = new ArrayList<>();
            switch (n) {
                case "java.util.LinkedHashMap": {
                    Value node = field(map, "head");
                    while (node instanceof ObjectReference && out.size() < MAX_ITEMS) {
                        Map<String, Value> f = fields((ObjectReference) node, "key", "value", "after");
                        out.add(new Value[] {f.get("key"), f.get("value")});
                        node = f.get("after");
                    }
                    return out;
                }
                case "java.util.HashMap": {
                    Value table = field(map, "table");
                    if (!(table instanceof ArrayReference) || ((ArrayReference) table).length() == 0) {
                        return out;
                    }
                    for (Value bucket : ((ArrayReference) table).getValues()) {
                        Value node = bucket;
                        while (node instanceof ObjectReference && out.size() < MAX_ITEMS) {
                            Map<String, Value> f = fields((ObjectReference) node, "key", "value", "next");
                            out.add(new Value[] {f.get("key"), f.get("value")});
                            node = f.get("next");
                        }
                        if (out.size() >= MAX_ITEMS) {
                            break;
                        }
                    }
                    return out;
                }
                case "java.util.TreeMap": {
                    Deque<ObjectReference> stack = new ArrayDeque<>();
                    Value node = field(map, "root");
                    while ((node instanceof ObjectReference || !stack.isEmpty()) && out.size() < MAX_ITEMS) {
                        while (node instanceof ObjectReference) {
                            stack.push((ObjectReference) node);
                            node = field((ObjectReference) node, "left");
                        }
                        ObjectReference top = stack.pop();
                        Map<String, Value> f = fields(top, "key", "value", "right");
                        out.add(new Value[] {f.get("key"), f.get("value")});
                        node = f.get("right");
                    }
                    return out;
                }
                case "java.util.ImmutableCollections$MapN": {
                    Value table = field(map, "table");
                    if (table instanceof ArrayReference) {
                        List<Value> t = ((ArrayReference) table).getValues();
                        for (int i = 0; i + 1 < t.size() && out.size() < MAX_ITEMS; i += 2) {
                            if (t.get(i) != null) {
                                out.add(new Value[] {t.get(i), t.get(i + 1)});
                            }
                        }
                    }
                    return out;
                }
                case "java.util.ImmutableCollections$Map1": {
                    Map<String, Value> f = fields(map, "k0", "v0");
                    out.add(new Value[] {f.get("k0"), f.get("v0")});
                    return out;
                }
                default:
                    return out;
            }
        }
    }

    // ---------------------------------------------------------------- json

    static final class Json {
        static String write(Object value) {
            StringBuilder sb = new StringBuilder();
            write(sb, value);
            return sb.toString();
        }

        @SuppressWarnings("unchecked")
        static void write(StringBuilder sb, Object v) {
            if (v == null) {
                sb.append("null");
            } else if (v instanceof Raw) {
                sb.append(((Raw) v).json);
            } else if (v instanceof String) {
                string(sb, (String) v);
            } else if (v instanceof Boolean || v instanceof Long || v instanceof Integer) {
                sb.append(v);
            } else if (v instanceof Double) {
                sb.append(Double.toString((Double) v));
            } else if (v instanceof Map) {
                sb.append('{');
                boolean first = true;
                for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                    if (!first) {
                        sb.append(',');
                    }
                    first = false;
                    string(sb, e.getKey());
                    sb.append(':');
                    write(sb, e.getValue());
                }
                sb.append('}');
            } else if (v instanceof List) {
                sb.append('[');
                boolean first = true;
                for (Object item : (List<Object>) v) {
                    if (!first) {
                        sb.append(',');
                    }
                    first = false;
                    write(sb, item);
                }
                sb.append(']');
            } else {
                string(sb, String.valueOf(v));
            }
        }

        static void string(StringBuilder sb, String s) {
            sb.append('"');
            for (int i = 0; i < s.length(); i++) {
                char c = s.charAt(i);
                switch (c) {
                    case '"': sb.append("\\\""); break;
                    case '\\': sb.append("\\\\"); break;
                    case '\n': sb.append("\\n"); break;
                    case '\r': sb.append("\\r"); break;
                    case '\t': sb.append("\\t"); break;
                    default:
                        if (c < 0x20 || (c >= 0xD800 && c <= 0xDFFF)) {
                            sb.append(String.format("\\u%04x", (int) c));
                        } else {
                            sb.append(c);
                        }
                }
            }
            sb.append('"');
        }
    }
}
