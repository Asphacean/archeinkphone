#!/usr/bin/env python3
"""Snapshot MSM DSI0 controller/PHY error registers on the Palma 2 via /dev/mem.

Masks the DSI error IRQ for a short window so the sticky error bits accumulate
instead of being cleared by the kernel ISR, prints them decoded, restores the mask.
Run as root:  python3 palma_dsi_errs.py [window_ms]
"""
import mmap, os, struct, sys, time

CTRL_BASE, CTRL_SHIFT = 0xae94000, 4      # DSI 6G: registers start at +4
PHY_BASE = 0xae94400                       # 7nm PHY CMN block
WINDOW_MS = int(sys.argv[1]) if len(sys.argv) > 1 else 200

CTRL_REGS = {'CTRL': 0x000, 'STATUS0': 0x004, 'FIFO_STATUS': 0x008, 'VID_CFG0': 0x00c,
             'ACK_ERR_STATUS': 0x064, 'LANE_STATUS': 0x0a4, 'LANE_CTRL': 0x0a8,
             'DLN0_PHY_ERR': 0x0b0, 'LP_TIMER_CTRL': 0x0b4, 'HS_TIMER_CTRL': 0x0b8,
             'TIMEOUT_STATUS': 0x0bc, 'CLKOUT_TIMING_CTRL': 0x0c0, 'EOT_PACKET_CTRL': 0x0c8,
             'ERR_INT_MASK0': 0x108, 'INTR_CTRL': 0x10c, 'CLK_STATUS': 0x11c}
BITS = {
    'FIFO_STATUS': {0: 'VIDEO_MDP_FIFO_OVERFLOW', 3: 'VIDEO_MDP_FIFO_UNDERFLOW', 7: 'CMD_MDP_FIFO_UNDERFLOW',
                    8: 'CMD_DMA_FIFO_RD_WM', 9: 'CMD_DMA_FIFO_WR_WM', 10: 'CMD_DMA_FIFO_UNDERFLOW',
                    12: 'DLN0_LP_FIFO_EMPTY', 13: 'DLN0_LP_FIFO_FULL'},
    'DLN0_PHY_ERR': {0: 'ERR_ESC', 4: 'ERR_SYNC_ESC', 8: 'ERR_CONTROL', 12: 'ERR_CONTENTION_LP0', 16: 'ERR_CONTENTION_LP1'},
    'TIMEOUT_STATUS': {0: 'HS_TX_TIMEOUT', 4: 'LP_RX_TIMEOUT', 8: 'BTA_TIMEOUT'},   # bit names per downstream
    'INTR_CTRL': {0: 'CMD_DMA_DONE', 1: 'MASK_CMD_DMA_DONE', 8: 'CMD_MDP_DONE', 9: 'MASK_CMD_MDP_DONE',
                  16: 'VIDEO_DONE', 17: 'MASK_VIDEO_DONE', 20: 'BTA_DONE', 21: 'MASK_BTA_DONE',
                  24: 'ERROR', 25: 'MASK_ERROR'},
}
IRQ_STATUS_BITS = (1 << 0) | (1 << 8) | (1 << 16) | (1 << 20) | (1 << 24)   # W1C, never write them back
MASK_ERROR = 1 << 25
PHY_REGS = {'CMN_GLBL_CTRL': 0x18, 'CMN_VREG_CTRL_0': 0x20, 'CMN_CTRL_0': 0x24, 'CMN_LANE_CFG0': 0x34,
            'CMN_LANE_CFG1': 0x38, 'CMN_LANE_CTRL0': 0xa0, 'CMN_PHY_STATUS': 0x140}
PHY_TIMING0 = 0xb4   # CMN_TIMING_CTRL_0 .. _13 = 0xb4 + 4*n (dsi_phy_7nm.xml)

def decode(name, v):
    names = [n for b, n in BITS.get(name, {}).items() if v & (1 << b)]
    return ' '.join(names)

def main():
    fd = os.open('/dev/mem', os.O_RDWR | os.O_SYNC)
    ctrl = mmap.mmap(fd, 0x2000, offset=CTRL_BASE)   # one page-aligned map covers ctrl (+0) and PHY (+0x400)
    phy = memoryview(ctrl)[PHY_BASE - CTRL_BASE:]
    rd = lambda m, o: struct.unpack('<I', bytes(m[o:o + 4]))[0]
    def wr(m, o, v): m[o:o + 4] = struct.pack('<I', v)
    c = lambda o: rd(ctrl, CTRL_SHIFT + o)

    print('-- PHY timing CTRL_0..13:', ' '.join('%02x' % rd(phy, PHY_TIMING0 + 4 * i) for i in range(14)))
    print('   stock              : 00 20 08 08 24 23 08 08 05 02 04 00 31 0e')
    for n, o in PHY_REGS.items():
        print('   %-16s 0x%08x' % (n, rd(phy, o)))
    print('-- ctrl snapshot:')
    for n, o in CTRL_REGS.items():
        v = c(o); print('   %-20s 0x%08x %s' % (n, v, decode(n, v)))

    # accumulate: mask the error IRQ so the ISR does not clear the sticky bits
    intr = c(CTRL_REGS['INTR_CTRL'])
    wr(ctrl, CTRL_SHIFT + CTRL_REGS['INTR_CTRL'], (intr & ~IRQ_STATUS_BITS) & ~MASK_ERROR)
    acc = {n: 0 for n in ('FIFO_STATUS', 'ACK_ERR_STATUS', 'DLN0_PHY_ERR', 'TIMEOUT_STATUS', 'CLK_STATUS', 'STATUS0')}
    t_end = time.monotonic() + WINDOW_MS / 1000.0
    while time.monotonic() < t_end:
        for n in acc:
            acc[n] |= c(CTRL_REGS[n])
    print('-- accumulated over %d ms (error IRQ masked):' % WINDOW_MS)
    for n, v in acc.items():
        print('   %-20s 0x%08x %s' % (n, v, decode(n, v)))
    # clear the sticky bits and re-enable the error IRQ
    for n in ('FIFO_STATUS', 'DLN0_PHY_ERR', 'TIMEOUT_STATUS'):
        wr(ctrl, CTRL_SHIFT + CTRL_REGS[n], acc[n])
    wr(ctrl, CTRL_SHIFT + CTRL_REGS['ACK_ERR_STATUS'], acc['ACK_ERR_STATUS']); wr(ctrl, CTRL_SHIFT + CTRL_REGS['ACK_ERR_STATUS'], 0)
    wr(ctrl, CTRL_SHIFT + CTRL_REGS['INTR_CTRL'], (c(CTRL_REGS['INTR_CTRL']) & ~IRQ_STATUS_BITS) | MASK_ERROR)
    print('   error IRQ re-enabled, INTR_CTRL=0x%08x' % c(CTRL_REGS['INTR_CTRL']))

if __name__ == '__main__':
    main()
