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
	{ 0x0ae94000, 0x1000, "dsi0" },      /* ctrl +0x000, phy cmn +0x400, lanes +0x600, pll +0x900 */
	{ 0x0ae6b800, 0x0300, "intf1" },     /* DPU INTF_1 (0xae01000 + 0x6a800) */
	{ 0x0ae01000, 0x0500, "mdptop" },
};

int init_module(void)
{
	volatile u32 *c = __ioremap(0x0ae94000, 0x1000, PROT_DEVICE_nGnRE);
	unsigned int i, k;
	u32 v, acc;

	if (!c)
		return -12;
	/* 6G ctrl: FIFO_STATUS at +4+0x8 = 0x0c, TIMEOUT 0xc0, DLN0_PHY_ERR 0xb4, ERR_INT_MASK0 0x10c (word index = off/4) */
	printk("\0016palmafifo pre fifo=%08x mask=%08x intr=%08x\n", c[0x0c / 4], c[0x10c / 4], c[0x110 / 4]);
	for (i = 0; i < 40; i++) {
		c[0x0c / 4] = 0xffffffff;          /* W1C */
		acc = 0;
		for (k = 0; k < 200000; k++) {     /* ~ tens of ms of bus reads */
			v = c[0x0c / 4];
			acc |= v;
		}
		printk("\0016palmafifo %02u fifo=%08x acc=%08x to=%08x dln0=%08x\n", i, v, acc, c[0xc0 / 4], c[0xb4 / 4]);
	}
	return -11;
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
	"name=palmafifo\0"
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
	.name = "palmafifo",
	.init = init_module,
	.exit = cleanup_module,
};

__asm__(".section .plt,\"aw\",%nobits\n.space 1\n"
	".section .init.plt,\"aw\",%nobits\n.space 1\n"
	".section .text.ftrace_trampoline,\"aw\",%nobits\n.space 1\n"
	".text\n");
