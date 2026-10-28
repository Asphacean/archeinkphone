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


#ifndef LOGMASK_ADDR
#define LOGMASK_ADDR 0
#endif
#define SECONDS 14
#define MAXENT 32768
#define PERCAP 24
struct ent { u64 t; u32 off; u32 val; };
static struct ent ents[MAXENT];
static u32 last[0x1000 / 4];
static unsigned char cnt[0x1000 / 4];

static inline u64 now(void) { u64 v; __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(v)); return v; }

static int sampled(unsigned int o)
{
	return o < 0x300 || (o >= 0x400 && o < 0x500) || (o >= 0x600 && o < 0x880) || (o >= 0xa00 && o < 0xbc0);
}

int init_module(void)
{
	volatile u32 *d = __ioremap(0x0ae94000, 0x1000, PROT_DEVICE_nGnRE);
	volatile u32 *cc = __ioremap(0x0af00000, 0x2000, PROT_DEVICE_nGnRE);
	u64 t0, end;
	unsigned int n = 0, o, i, sweeps = 0, offsweeps = 0;
	int powered = -1;

	if (!d || !cc)
		return -12;
	if (LOGMASK_ADDR)
		*(volatile u32 *)LOGMASK_ADDR = 0xffffffff;
	t0 = now();
	end = t0 + (u64)SECONDS * 19200000;
	while (now() < end && n < MAXENT) {
		/* only touch DSI while MDSS GDSC is on and the MDSS AHB branch clock runs */
		int on = (cc[0x1004 / 4] & 0x80000000u) && !(cc[0x104c / 4] & 0x80000000u);
		if (on != powered) {
			ents[n].t = now() - t0; ents[n].off = 0xffff; ents[n].val = on; n++;
			powered = on;
		}
		if (!on) { offsweeps++; continue; }
		for (o = 0; o < 0x1000 && n < MAXENT; o += 4) {
			u32 v;
			if (!sampled(o))
				continue;
			v = d[o / 4];
			if (v != last[o / 4] && cnt[o / 4] < PERCAP) {
				ents[n].t = now() - t0; ents[n].off = o; ents[n].val = v; n++;
				last[o / 4] = v; cnt[o / 4]++;
			}
		}
		sweeps++;
	}
	printk("\0016PT begin entries=%u sweeps=%u offsweeps=%u\n", n, sweeps, offsweeps);
	for (i = 0; i < n; i++)
		printk("\0016PT %lu %03x %08x\n", (unsigned long)(ents[i].t * 10 / 192), ents[i].off, ents[i].val);
	printk("\0016PT end\n");
	if (LOGMASK_ADDR)
		*(volatile u32 *)LOGMASK_ADDR = 0;
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
	"name=palmatrace\0"
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
	.name = "palmatrace",
	.init = init_module,
	.exit = cleanup_module,
};

__asm__(".section .plt,\"aw\",%nobits\n.space 1\n"
	".section .init.plt,\"aw\",%nobits\n.space 1\n"
	".section .text.ftrace_trampoline,\"aw\",%nobits\n.space 1\n"
	".text\n");
