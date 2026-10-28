# Ghidra headless script: for every symbol matching a regex, ensure a function exists there, decompile it,
# write one .c per function. Works without full auto-analysis (-noanalysis) thanks to kernel symbols.
# Usage: analyzeHeadless ... -postScript ghidra_decomp.py <regex> <outdir>
import re, os
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.symbol import SymbolType

args = getScriptArgs()
pat = re.compile(args[0]); out = args[1]
if not os.path.isdir(out): os.makedirs(out)
fm = currentProgram.getFunctionManager()
ifc = DecompInterface(); ifc.openProgram(currentProgram)
mon = ConsoleTaskMonitor(); n = 0; fails = 0
for s in currentProgram.getSymbolTable().getSymbolIterator():
    name = s.getName()
    if not pat.search(name): continue
    if s.getSymbolType() not in (SymbolType.FUNCTION, SymbolType.LABEL): continue
    a = s.getAddress()
    if not currentProgram.getMemory().getBlock(a) or not currentProgram.getMemory().getBlock(a).isExecute(): continue
    f = fm.getFunctionAt(a)
    if f is None:
        f = createFunction(a, name)
    if f is None: continue
    r = ifc.decompileFunction(f, 180, mon)
    if r.decompileCompleted():
        code = r.getDecompiledFunction().getC()
    else:
        code = "// FAILED: " + str(r.getErrorMessage()); fails += 1
    open(os.path.join(out, name + ".c"), "w").write(code); n += 1
print("decompiled %d functions (%d failed) -> %s" % (n, fails, out))
