//MoveBlock.java
//@category H3Plus
//Relocate a raw-binary import of the H3 Plus app to its true VA.
//The BinaryLoader ignores -loader-"Base Address" headless, so import raw
//and move the block here: app offset 0 == flash 0x5000 == VA 0x01E00000.
//SPDX-License-Identifier: MIT
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.*;

public class MoveBlock extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        MemoryBlock block = mem.getBlocks()[0];
        long size = block.getSize();
        String name = block.getName();
        byte[] buf = new byte[(int) size];
        mem.getBytes(block.getStart(), buf);
        mem.removeBlock(block, monitor);
        Address base = currentProgram.getAddressFactory()
            .getDefaultAddressSpace().getAddress(0x01E00000L);
        mem.createInitializedBlock(name, base,
            new java.io.ByteArrayInputStream(buf), size, monitor, false);
        println("Moved block " + name + " size=" + size + " -> " + base);
    }
}
