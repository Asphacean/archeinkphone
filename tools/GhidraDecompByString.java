// Headless Ghidra script: find defined strings matching a regex, decompile every function that references them.
// Usage: ... -postScript GhidraDecompByString.java <regex> <outdir>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.File;
import java.io.FileWriter;
import java.util.*;
import java.util.regex.Pattern;

public class GhidraDecompByString extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Pattern pat = Pattern.compile(a[0]);
        File out = new File(a[1]); out.mkdirs();
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        Map<Function, List<String>> hits = new LinkedHashMap<>();
        DataIterator di = listing.getDefinedData(true);
        while (di.hasNext()) {
            Data d = di.next();
            if (!d.hasStringValue()) continue;
            String s = d.getDefaultValueRepresentation();
            if (!pat.matcher(s).find()) continue;
            ReferenceIterator ri = currentProgram.getReferenceManager().getReferencesTo(d.getAddress());
            while (ri.hasNext()) {
                Reference r = ri.next();
                Function f = fm.getFunctionContaining(r.getFromAddress());
                if (f == null) continue;
                hits.computeIfAbsent(f, k -> new ArrayList<>()).add(s.length() > 60 ? s.substring(0, 60) : s);
            }
        }
        DecompInterface ifc = new DecompInterface(); ifc.openProgram(currentProgram);
        try (FileWriter idx = new FileWriter(new File(out, "INDEX.txt"))) {
            for (Map.Entry<Function, List<String>> e : hits.entrySet()) {
                Function f = e.getKey();
                DecompileResults r = ifc.decompileFunction(f, 240, monitor);
                String code = r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// FAILED: " + r.getErrorMessage();
                String name = f.getName() + "_" + f.getEntryPoint();
                try (FileWriter w = new FileWriter(new File(out, name + ".c"))) { w.write("// strings: " + e.getValue() + "\n" + code); }
                idx.write(name + "\t" + e.getValue() + "\n");
            }
        }
        println("decompiled " + hits.size() + " functions -> " + out);
    }
}
