// Headless Ghidra script: for every symbol matching a regex, ensure a function exists, decompile, write <name>.c
// Usage: analyzeHeadless <proj> <name> -process vmlinux.elf -noanalysis -scriptPath <dir> -postScript GhidraDecomp.java <regex> <outdir>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolType;
import java.io.File;
import java.io.FileWriter;
import java.util.regex.Pattern;

public class GhidraDecomp extends GhidraScript {
    public void run() throws Exception {
        String[] a = getScriptArgs();
        Pattern pat = Pattern.compile(a[0]);
        File out = new File(a[1]); out.mkdirs();
        FunctionManager fm = currentProgram.getFunctionManager();
        DecompInterface ifc = new DecompInterface(); ifc.openProgram(currentProgram);
        int n = 0, fails = 0;
        for (Symbol s : currentProgram.getSymbolTable().getSymbolIterator()) {
            String name = s.getName();
            if (!pat.matcher(name).find()) continue;
            SymbolType t = s.getSymbolType();
            if (t != SymbolType.FUNCTION && t != SymbolType.LABEL) continue;
            Address addr = s.getAddress();
            if (currentProgram.getListing().getDefinedDataAt(addr) != null) continue; // data object, not code
            Function f = fm.getFunctionAt(addr);
            if (f == null) f = createFunction(addr, name);
            if (f == null) continue;
            DecompileResults r = ifc.decompileFunction(f, 180, monitor);
            String code;
            if (r.decompileCompleted()) code = r.getDecompiledFunction().getC();
            else { code = "// FAILED: " + r.getErrorMessage(); fails++; }
            try (FileWriter w = new FileWriter(new File(out, name + ".c"))) { w.write(code); }
            n++;
        }
        println("decompiled " + n + " functions (" + fails + " failed) -> " + out);
    }
}
