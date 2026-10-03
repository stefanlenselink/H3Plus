//DumpDecompiled.java
//@category H3Plus
//Decompile functions to C files.  Script args:
//  <outDir> [addr ...]   (addresses default to the BT-research set)
//SPDX-License-Identifier: MIT
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
import java.io.*;
import java.nio.file.*;

public class DumpDecompiled extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outDir = args.length > 0 ? args[0] : ".";
        String[] targets = args.length > 1
            ? java.util.Arrays.copyOfRange(args, 1, args.length)
            : new String[] { "01e1787c", "01e7ec28", "01e21af8",
                             "01e182b0", "01e17a26" };
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        File out = new File(outDir);
        AddressSpace sp = currentProgram.getAddressFactory().getDefaultAddressSpace();
        for (String t : targets) {
            Address a = sp.getAddress(t);
            Function f = currentProgram.getFunctionManager().getFunctionAt(a);
            if (f == null) { println("No function at " + t); continue; }
            DecompileResults r = decomp.decompileFunction(f, 120, monitor);
            String c = r.decompileCompleted()
                ? r.getDecompiledFunction().getC()
                : "FAILED: " + r.getErrorMessage();
            Files.writeString(new File(out, t + ".c").toPath(), c);
            println("Dumped " + t + " " + (r.decompileCompleted() ? "OK" : "FAIL"));
        }
    }
}
