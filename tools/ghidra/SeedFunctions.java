//SeedFunctions.java
//@category H3Plus
//Create functions in the H3 Plus app image: every 32-bit LE word in the
//image that points back into the code range is treated as a pointer-table
//entry (same trick as tools/findva.py) and gets a function; plus explicit
//seeds.  Run as a preScript so the standard analyzers propagate afterwards.
//SPDX-License-Identifier: MIT
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.Memory;

public class SeedFunctions extends GhidraScript {
    static final long START = 0x01E00000L;
    static final long END   = 0x01EC4000L;   // app end (flash 0xC8FE0)

    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        byte[] img = new byte[(int) (END - START)];
        mem.getBytes(sp.getAddress(START), img);

        java.util.TreeSet<Long> targets = new java.util.TreeSet<>();
        for (int a = 0; a + 3 < img.length; a += 2) {
            long v = (img[a] & 0xffL) | ((img[a + 1] & 0xffL) << 8)
                   | ((img[a + 2] & 0xffL) << 16) | ((img[a + 3] & 0xffL) << 24);
            if (v >= START + 2 && v < END) targets.add(v);
        }
        // well-known sites (findings ch. 22/23): classifier, conn readers,
        // ops handlers
        long[] seeds = { 0x01E1787CL, 0x01E7EC28L, 0x01E21AF8L,
                         0x01E182B0L, 0x01E17A26L, START };
        for (long s : seeds) targets.add(s);
        println("Pointer-scan candidates: " + targets.size());

        int made = 0;
        for (long t : targets) {
            if (monitor.isCancelled()) break;
            Address addr = sp.getAddress(t);
            try {
                disassemble(addr);
                Function f = getFunctionAt(addr);
                if (f == null) {
                    Function before = getFunctionBefore(addr);
                    if (before != null && before.getEntryPoint().equals(addr)) f = before;
                }
                if (f == null) {
                    createFunction(addr, null);
                    made++;
                }
            } catch (Exception e) { /* mid-function or bad decode */ }
            if (made % 2000 == 0) monitor.setMessage("functions: " + made);
        }
        println("Created functions: " + made);
    }
}
