// Headless: for each hex address in args[0] (comma-separated), list referencing functions and decompile them to args[1].
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;
public class GhidraXrefDecomp extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs(); File out = new File(a[1]); out.mkdirs();
        DecompInterface ifc = new DecompInterface(); ifc.openProgram(currentProgram);
        for (String hex : a[0].split(",")) {
            Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(Long.parseLong(hex, 16));
            Set<Function> fs = new LinkedHashSet<>();
            ReferenceIterator ri = currentProgram.getReferenceManager().getReferencesTo(addr);
            while (ri.hasNext()) { Reference r = ri.next(); Function f = currentProgram.getFunctionManager().getFunctionContaining(r.getFromAddress()); if (f != null) { fs.add(f); println(hex + " <- " + f.getName() + " @" + r.getFromAddress() + " " + r.getReferenceType()); } }
            for (Function f : fs) { DecompileResults r = ifc.decompileFunction(f, 240, monitor); String code = r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// FAILED"; try (FileWriter w = new FileWriter(new File(out, f.getName() + ".c"))) { w.write(code); } }
        }
    }
}
