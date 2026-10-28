/*
 * Out-of-tree register dump module for the STOCK Boox Palma 2 Android kernel
 * (4.19.157-perf, modversions, no module signing). Built without kernel
 * headers: struct module layout (size 0x340, init at 0x170, exit at 0x310)
 * and symbol CRCs are copied from the device's own vendor modules.
 * init_module() dumps the regions below to the kernel log and returns
 * -EAGAIN, so the module never stays loaded. ioremap mappings are leaked
 * on purpose (no __iounmap CRC available).
 */
typedef unsigned long u64;
typedef unsigned int u32;

extern int printk(const char *fmt, ...);
extern void *__ioremap(u64 phys, u64 size, u64 prot);

/* arm64 4.19 PROT_DEVICE_nGnRE = PROT_DEFAULT | PTE_PXN | PTE_UXN | PTE_DIRTY | PTE_WRITE | PTE_ATTRINDX(MT_DEVICE_nGnRE) */
#define PROT_DEVICE_nGnRE 0x00e8000000000707UL

static const struct { u64 base, len; const char *name; } regions[] = {
	{ 0x0af00000, 0x2000, "dispcc" },
};

int init_module(void)
{
	unsigned int r, i;

	for (r = 0; r < sizeof(regions) / sizeof(regions[0]); r++) {
		volatile u32 *p = __ioremap(regions[r].base, regions[r].len, PROT_DEVICE_nGnRE);

		if (!p) {
			printk("\0016palmacc: ioremap %s failed\n", regions[r].name);
			continue;
		}
		for (i = 0; i < regions[r].len / 4; i += 4)
			printk("\0016palmacc %s %08lx: %08x %08x %08x %08x\n", regions[r].name,
			       regions[r].base + i * 4, p[i], p[i + 1], p[i + 2], p[i + 3]);
	}
	printk("\0016palmacc: done\n");
	return -11; /* -EAGAIN: do not stay loaded */
}

void cleanup_module(void) { }

struct modversion_info { u64 crc; char name[64 - sizeof(u64)]; };
__attribute__((section("__versions"), used, aligned(8)))
static const struct modversion_info versions[] = {
	{ 0x19eaa1f8, "module_layout" },
	{ 0x7c32d0f0, "printk" },
	{ 0x6b4b2933, "__ioremap" },
};

__attribute__((section(".modinfo"), used, aligned(1)))
static const char modinfo[] =
	"license=GPL\0"
	"name=palmacc\0"
	"vermagic=4.19.157-perf-g5b5c12b83427 SMP preempt mod_unload modversions aarch64";

struct fake_module {
	char head[0x18];
	char name[0x170 - 0x18];
	int (*init)(void);
	char mid[0x310 - 0x178];
	void (*exit)(void);
	char tail[0x340 - 0x318];
};
__attribute__((section(".gnu.linkonce.this_module"), used, aligned(64)))
struct fake_module __this_module = {
	.name = "palmacc",
	.init = init_module,
	.exit = cleanup_module,
};

__asm__(".section .plt,\"aw\",%nobits\n.space 1\n"
	".section .init.plt,\"aw\",%nobits\n.space 1\n"
	".section .text.ftrace_trampoline,\"aw\",%nobits\n.space 1\n"
	".text\n");
