//DumpAll.java
//@category H3Plus
//Dump the whole app: per-function decompiled C, per-function asm, plus
//function/symbol/string indexes.  Script args: <outDir>
//Writes <outDir>/{decompiled/,decompiled_all.c,disasm/,functions.txt,
//                 symbols.txt,strings.txt}
//SPDX-License-Identifier: MIT
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.decompiler.parallel.DecompilerCallback;
import ghidra.app.decompiler.parallel.ParallelDecompiler;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.StringDataType;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.util.task.TaskMonitor;

import java.io.File;
import java.io.PrintWriter;
import java.io.FileWriter;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class DumpAll extends GhidraScript {
    static final long APP_VA = 0x01E00000L;
    static final long APP_FLASH = 0x5000L;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File out = new File(args.length > 0 ? args[0] : "disassembled");
        File cDir = new File(out, "decompiled");
        File aDir = new File(out, "disasm");
        cDir.mkdirs();
        aDir.mkdirs();

        Listing listing = currentProgram.getListing();
        List<Function> funcs = new ArrayList<>();
        FunctionIterator fit = listing.getFunctions(true);
        while (fit.hasNext()) {
            Function f = fit.next();
            if (!f.isExternal()) funcs.add(f);
        }
        funcs.sort(Comparator.comparingLong(f -> f.getEntryPoint().getUnsignedOffset()));
        println("DumpAll: " + funcs.size() + " functions");

        // ---- per-function asm + functions.txt index ----
        try (PrintWriter fw = pw(new File(out, "functions.txt"))) {
            fw.println("# addr      size  name");
            int n = 0;
            for (Function f : funcs) {
                if (monitor.isCancelled()) return;
                long entry = f.getEntryPoint().getUnsignedOffset();
                long size = f.getBody().getNumAddresses();
                try (PrintWriter a = pw(new File(aDir, fileBase(f) + ".asm"))) {
                    a.println("; " + f.getName() + " @ " + hex(entry)
                        + "  (flash " + hex(APP_FLASH + (entry - APP_VA)) + ")");
                    InstructionIterator it =
                        listing.getInstructions(f.getBody(), true);
                    while (it.hasNext()) {
                        a.println(fmtInsn(it.next()));
                    }
                }
                fw.printf("%08X %7d %s%n", entry, size, f.getName());
                if (++n % 1000 == 0) monitor.setMessage("asm: " + n);
            }
        }
        println("DumpAll: asm written");

        // ---- parallel decompile of every function ----
        DecompilerCallback<String[]> cb =
            new DecompilerCallback<String[]>(currentProgram, d -> { }) {
                @Override
                public String[] process(DecompileResults r, TaskMonitor m) {
                    Function f = r.getFunction();
                    String c = r.decompileCompleted()
                        ? r.getDecompiledFunction().getC()
                        : "/* DECOMPILE FAILED: " + r.getErrorMessage() + " */\n";
                    return new String[] { fileBase(f), c };
                }
            };
        cb.setTimeout(60);
        List<String[]> res =
            ParallelDecompiler.decompileFunctions(cb, funcs, monitor);
        res.sort(Comparator.comparing(p -> p[0]));
        int ok = 0;
        try (PrintWriter all = pw(new File(out, "decompiled_all.c"))) {
            for (String[] p : res) {
                Files.writeString(new File(cDir, p[0] + ".c").toPath(), p[1]);
                all.print(p[1]);
                if (!p[1].startsWith("/* DECOMPILE FAILED")) ok++;
            }
        }
        println("DumpAll: decompiled " + ok + "/" + res.size());

        // ---- symbols ----
        try (PrintWriter sw = pw(new File(out, "symbols.txt"))) {
            sw.println("# addr      type name");
            SymbolIterator sit =
                currentProgram.getSymbolTable().getAllSymbols(true);
            while (sit.hasNext()) {
                Symbol s = sit.next();
                sw.printf("%08X %-14s %s%n", s.getAddress().getUnsignedOffset(),
                    s.getSymbolType(), s.getName());
            }
        }

        // ---- defined strings ----
        try (PrintWriter sw = pw(new File(out, "strings.txt"))) {
            sw.println("# addr      flash     text");
            DataIterator dit = listing.getDefinedData(true);
            while (dit.hasNext()) {
                Data d = dit.next();
                DataType dt = d.getDataType();
                if (dt instanceof StringDataType && d.hasStringValue()) {
                    long a = d.getAddress().getUnsignedOffset();
                    sw.printf("%08X %8X  %s%n", a, APP_FLASH + (a - APP_VA),
                        d.getValue());
                }
            }
        }
        println("DumpAll: done");
    }

    static String fileBase(Function f) {
        long a = f.getEntryPoint().getUnsignedOffset();
        String n = f.getName().replaceAll("[^A-Za-z0-9_.-]", "_");
        return String.format("%08x_%s", a, n);
    }

    static String fmtInsn(Instruction i) throws Exception {
        byte[] b = i.getBytes();
        StringBuilder hexs = new StringBuilder();
        for (int k = 0; k < b.length && k < 8; k++) {
            hexs.append(String.format("%02x ", b[k] & 0xff));
        }
        long a = i.getAddress().getUnsignedOffset();
        return String.format("%08X  %-24s [%06X]  %s", a, hexs.toString().trim(),
            APP_FLASH + (a - APP_VA), i.toString());
    }

    static String hex(long v) {
        return String.format("0x%08X", v);
    }

    static PrintWriter pw(File f) throws java.io.IOException {
        return new PrintWriter(new FileWriter(f, false));
    }
}
