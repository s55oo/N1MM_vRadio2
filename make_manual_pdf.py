"""Builds vRadio_Manual.pdf (run: python make_manual_pdf.py)."""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

OUT = r"C:\Ham\vRadio\vRadio_Manual.pdf"
ACCENT = colors.HexColor("#1f4e79")
LIGHT = colors.HexColor("#eef3f8")
CODEBG = colors.HexColor("#f4f4f4")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=22, textColor=ACCENT, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontSize=10.5, textColor=colors.grey, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, textColor=ACCENT, spaceBefore=12, spaceAfter=6, keepWithNext=1)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=9.5, leading=13, spaceAfter=4)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.5, leading=11, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
CODE = ParagraphStyle("CODE", fontName="Courier", fontSize=7.8, leading=10, backColor=CODEBG,
                      borderPadding=(5, 5, 5, 5), spaceBefore=4, spaceAfter=8, leftIndent=4)
CAPTION = ParagraphStyle("CAPTION", parent=ss["Normal"], fontSize=8, textColor=colors.grey, spaceBefore=2,
                         spaceAfter=10, alignment=1)
BULLET = ParagraphStyle("BULLET", parent=BODY, leftIndent=12, bulletIndent=2)


def p(t, st=BODY):
    return Paragraph(t, st)


def code(t):
    return Preformatted(t, CODE, maxLineLength=118)


def bullets(items):
    return [Paragraph(i, BULLET, bulletText="\u2022") for i in items]


def table(rows, widths):
    data = [[Paragraph(c, CELLB) for c in rows[0]]] + \
           [[Paragraph(c, CELL) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d3df")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "img")


def pic(name, caption, width=170 * mm):
    """Screenshot scaled to the given width (never upscaled), with a caption under it."""
    from reportlab.lib.utils import ImageReader
    path = os.path.join(IMG, name)
    w, h = ImageReader(path).getSize()
    w_pt = min(width, w * 0.75)                     # 96 dpi screenshot -> points
    return KeepTogether([Image(path, width=w_pt, height=h * w_pt / w), p("<i>" + caption + "</i>", CAPTION)])


def c(t):  # inline code
    return f'<font name="Courier">{t}</font>'


FULL = (r"C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064" "\n"
        r"    --dual-rx --dual-rx-cmd FR00; -v --log C:\Ham\vRadio\dist\vradio_test_log.txt")
NORMAL = (r"C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064" "\n"
          r"    --dual-rx --dual-rx-cmd FR00;")
NODUAL = r"C:\Ham\vRadio\dist\vRadio.exe --tcp 4532 --follow-band --auto-split --n1mm-udp 12064"
DIAGRAM = """FTDX101D --- COM14 38400 8N1 ---> vRadio.exe --- TCP 127.0.0.1:4532 ---> N1MM radio 2 (TS-2000)
                                      ^
                                      +--- UDP 12064 <--- N1MM RadioInfo broadcast (TX focus)"""

story = [
    p("vRadio", H1),
    p("Yaesu FTDX101D as a Kenwood TS-2000 for N1MM Logger+ &nbsp;|&nbsp; manual for v1.0.7, 12 Nov 2026", SUB),
    p("vRadio connects to the FTDX101D on <b>COM14 (38400 8N1)</b> and presents the radio's "
      "<b>VFO-B (SUB)</b> to N1MM Logger+ as <b>radio 2</b>, a Kenwood TS-2000, over <b>TCP port 4532</b>. "
      "N1MM radio 1 stays on its own connection to the radio's VFO-A (MAIN)."),
    code(DIAGRAM),
    p("<b>One PC or two PCs:</b> " + c("pcs = 1") + " (default) = this PC's N1MM runs both radios (SO2R). "
      + c("pcs = 2") + " = a second PC's N1MM is radio 2 over the LAN. The two-PC station setup "
      "(microHAM, VSPE, N1MM, shared WinKeyer) with screenshots is in section 9."),

    p("1. Start vRadio", H2),
    p("Double-click " + c(r"dist\vRadio_TEST.bat") + ", or run the full working command (with debug log):"),
    code(FULL),
    p("Normal use, without the debug log:"),
    code(NORMAL),
    p("Without dual RX (if " + c("FR00;") + " turns out to be wrong):"),
    code(NODUAL),
    p("System tray version", H3),
    p("Double-click " + c(r"dist\vRadio Tray.lnk") + " (runs " + c(r"dist\vRadioTray.exe")
      + " with the normal-use options above). It has no console window and sits in the system tray "
      "next to the clock. Start with Windows: copy the shortcut into the Startup folder (Win+R, "
      + c("shell:startup") + ")."),
    table([["Icon", "Meaning"],
           ["green", "radio answers"],
           ["red", "radio not answering, or an error (hover or right-click for details)"],
           ["orange", "transmitting"],
           ["grey", "starting / connecting"]],
          [30 * mm, 140 * mm]),
    Spacer(1, 4),
    p("Right-click menu: radio status, N1MM connection, TX focus, <i>Copy VFO-A -&gt; VFO-B (same band)</i>, "
      "<i>Open log</i>, <i>Open vRadio folder</i>, <i>Exit vRadio</i>. Log: " + c(r"dist\vradio_log.txt")
      + " (rotating, max 4 x 2 MB). Only one vRadioTray can run at a time. Same options as vRadio.exe."),
    p("<b>Updates:</b> vRadio checks GitHub Releases at start and every 6 h. Tray: a notification and "
      "<i>Install update</i> in the menu (restarts with the same options, refused while transmitting), "
      "plus <i>Check for updates</i>. Console: " + c("vRadio.exe --update") + ". " + c("--auto-update")
      + " installs at start, before the radio connects (used by the shortcut). The old exe is kept as "
      + c(".old") + " until the next start."),
    p("<b>Settings file:</b> put the options in " + c("vradio.ini") + " next to the exe, section "
      + c("[vradio]") + ", keys = long option names (" + c("n1mm_udp = 12064") + ", " + c("follow_band = yes")
      + "). Command-line options override it. " + c("--write-config") + " saves the given options to it; "
      + c("--config FILE") + " uses another file; " + c("--no-config") + " ignores it. Every setting is "
      "explained in " + c(r"dist\vradio.example.ini") + ". Tray: <i>Edit settings</i>, then "
      "<i>Restart vRadio</i>."),
    p("<b>UDP 12064:</b> 12060-12063 are used by Callbooker, QSOrouter, POUNCer and PingPong; only one "
      "program gets each packet on a port. Add " + c("127.0.0.1:12064") + " to N1MM Broadcast Data &gt; Radio."),
    p("Radio on another port: put the port and speed first, e.g.:"),
    code(r"C:\Ham\vRadio\dist\vRadio.exe COM5 38400 --tcp 4532 --follow-band --auto-split --n1mm-udp 12064"),
    p("Stop: close the vRadio window or press Ctrl+C. Only one program can use COM14 at a time."),

    p("2. N1MM setup", H2),
    table([["Where", "Setting"],
           ["Configurer > Hardware, radio 2", "Port <b>TCP</b>, Radio <b>Kenwood TS-2000</b>, "
                                              "IP <b>127.0.0.1</b>, port <b>4532</b>"],
           ["Configurer > Broadcast Data", "<b>Radio</b> ticked, address <b>127.0.0.1:12064</b> "
                                           "(vRadio reads the TX focus from it)"]],
          [55 * mm, 115 * mm]),

    p("3. How it works", H2),
    p("Same band for both radios", H3),
    p("N1MM refuses to put radio 1 and radio 2 on one band (\"Can not set both radios to the same band!\"), "
      "but accepts it when the radio does it. With " + c("--follow-band") + ", every time VFO-A changes band "
      "vRadio sends " + c("AB;") + " (copy VFO-A to VFO-B, frequency and mode). You can still tune radio 2 "
      "anywhere afterwards."),
    p("Auto split by N1MM TX focus", H3),
    *bullets([
        "N1MM keys most transmissions (WinKeyer CW) without CAT, so vRadio follows N1MM's "
        "<b>TX focus</b> (" + c("ActiveRadioNr") + " in the RadioInfo UDP broadcast).",
        "Radio 2 has TX focus: vRadio sends " + c("ST1;") + " - TX on VFO-B.",
        "Radio 1 has TX focus: vRadio sends " + c("ST0;") + " - split off, TX on VFO-A.",
        "A focus change during a transmission waits until the radio is back on RX. "
        "After every TX-to-RX the TX VFO is set again.",
        "N1MM sees radio 2 as a plain, non-split radio.",
    ]),
    p("Dual RX", H3),
    p("With " + c("--dual-rx") + ", vRadio reads " + c("FR;") + " 4 times a second and re-sends "
      + c("--dual-rx-cmd") + " (" + c("FR00;") + ") if the radio reports something else. "
      "This overrides manual dual-RX toggles."),

    p("4. All options", H2),
    table([["Option", "Effect"],
           [c("COM5 38400") + " (first, no dashes)", "Radio port and speed, e.g. " + c("vRadio.exe COM5 38400 --tcp 4532")
            + ". Same as --radio / --radio-baud. Default COM14 38400."],
           [c("--tcp 4532"), "Serve the TS-2000 emulation on TCP 4532 instead of a COM port."],
           [c("--pcs 1 / --pcs 2"), "1 = one PC (SO2R). 2 = two PCs: TCP 4532 on 0.0.0.0, auto split only "
                                     "during the other PC's CAT TX, follow-band and N1MM UDP off (section 9)."],
           [c("--tcp-host 0.0.0.0"), "Accept TCP from other PCs (default 127.0.0.1 = this PC only). "
                                     "Allow vRadio.exe in Windows Firewall."],
           [c("--vfo B"), "Default. N1MM VFO-A = radio VFO-B (SUB), N1MM VFO-B = radio VFO-A. "
                          + c("--vfo A") + " = normal mapping."],
           [c("--follow-band"), "When radio VFO-A changes band, VFO-B jumps to that band (" + c("AB;") + ")."],
           [c("--same-band"), "Copy VFO-A to VFO-B once at startup."],
           [c("--auto-split"), "vRadio sets the TX VFO itself (" + c("ST1;") + " = VFO-B, " + c("ST0;")
                               + " = VFO-A). CAT " + c("TX;") + " from radio 2 transmits on VFO-B."],
           [c("--n1mm-udp 12064"), "With --auto-split: follow N1MM TX focus from the RadioInfo broadcast."],
           [c("--n1mm-radio 2"), "Which N1MM radio number vRadio is (default 2)."],
           [c("--dual-rx"), "Keep dual receive on."],
           [c("--dual-rx-cmd FR00;"), "Command for dual receive (default FR00;, verify on site)."],
           [c("--tx-follow"), "At startup set TX to the controlled VFO. Ignored with --auto-split."],
           [c("--usb-data / --lsb-data"), "USB/LSB from the software selects DATA-U/DATA-L (FT8 etc.)."],
           [c("--radio COM14 --radio-baud 38400"), "Radio port and speed (defaults)."],
           [c("--cat COM1 --cat-baud 38400"), "COM-port mode instead of TCP (software uses COM2 of the VSPE pair)."],
           [c("-v / --log FILE"), "Log every command / also write the log to a file (rotating, 4 x 2 MB)."],
           [c("--tray"), "Run as a tray icon (vRadioTray.exe always does)."]],
          [55 * mm, 115 * mm]),
    Spacer(1, 4),
    p("N1MM macro: " + c("{CAT2ASC VRAB;}") + " copies VFO-A to VFO-B on a key press."),

    p("5. Files", H2),
    table([["File", "Purpose"],
           [c(r"dist\vRadio.exe"), "The translator, console version (no Python needed)."],
           [c(r"dist\vRadioTray.exe"), "The same, as a system tray app (no console)."],
           [c(r"dist\vRadio Tray.lnk"), "Shortcut: vRadioTray with the full working options."],
           [c(r"dist\vRadio_TEST.bat"), "Full working setup with debug log."],
           [c(r"dist\vRadio_N1MM_TCP.bat"), "Older launcher: TCP + follow-band only (no auto-split)."],
           [c(r"dist\radio_monitor.exe / .bat"), "Read-only monitor of FR/FT/ST/VS/TX/FA/FB/MD; prints every "
                                                 "change. Stop vRadio first."],
           [c(r"dist\update_vRadio.bat"), r"Copies dist\new\vRadio.exe over dist\vRadio.exe after a rebuild."],
           [c("vradio.py"), "Source code."],
           [c("probe_yaesu.py, test_client.py, test_tcp.py"), "Small test tools (Python)."],
           [c("README.md, SETUP_2PC.md, NOTES_auto_split.md"), "Documentation, two-PC setup, background notes."],
           [c("make_manual_pdf.py"), "Builds this PDF."]],
          [70 * mm, 100 * mm]),

    p("6. Rebuild the exe", H2),
    code('cd C:\\Ham\\vRadio\n"%LOCALAPPDATA%\\Programs\\Python\\Python312\\python.exe" -m PyInstaller\n'
         '    --onefile --console --icon vradio.ico --name vRadio vradio.py\n'
         '"%LOCALAPPDATA%\\Programs\\Python\\Python312\\python.exe" -m PyInstaller\n'
         '    --onefile --windowed --icon vradio.ico --name vRadioTray vradio.py'),
    p("(Two commands, each written on two lines here.) Then rebuild this manual with "
      + c("python make_manual_pdf.py") + "."),
    p("Python 3.12, pyserial and PyInstaller are installed for this Windows user."),

    p("7. TS-2000 commands supported", H2),
    p("ID, TY, AI (emulated by polling), PS, FA, FB, IF, MD, TX, RX, FT, FR, VV, SM (0-255 to 0-30), AG, RG, "
      "SQ, PC, KS, VX, NB, NR, PA, RA, RT, XT, RC, RU, RD, BY, UP, DN, plus vRadio's own VRAB. "
      "Anything else is answered " + c("?;") + ". Not mapped: KY (CW text), SH/SL (filters), EX (menu)."),

    p("8. Troubleshooting and open items", H2),
    table([["Problem", "What to do"],
           ["COM14 busy", "A vRadio or radio_monitor is still running. Close it, or end vRadio.exe in "
                          "Task Manager (the one-file exe runs as two processes; end both)."],
           ["Radio does not answer (no ID0681;)", "COM14 is an ELTIMA virtual port, not the radio's USB. "
                                                  "Start the program that links COM14 to the radio; check the "
                                                  "radio is on."],
           ["\"Can not set both radios to the same band!\"", "Use --follow-band or the VRAB macro."],
           ["TX on the wrong VFO", "Check N1MM Broadcast Data > Radio > 127.0.0.1:12064 and look for "
                                   "\"N1MM TX focus\" lines in the log."]],
          [55 * mm, 115 * mm]),
    PageBreak(),
    p("9. Two PCs on one FTDX101D (pcs = 2)", H2),
    p("Laptop 1 runs vRadio (" + c("vRadioDJ.exe") + " with the DJ Control MP3 e2, or " + c("vRadioTray.exe")
      + ") and N1MM radio 1 on VFO-A. Laptop 2's N1MM is radio 2 on VFO-B over the LAN. The DJ console is "
      "always connected to laptop 1; its left jog wheel tunes VFO-B there."),
    code("""Laptop 1 (vRadio)                                     Laptop 2
  N1MM radio 1 = FTDX101D (VFO-A) - COM10
  vRadio (pcs = 2) --- COM14 - VFO-B
     TCP 4532  <----------------- LAN -----------------  N1MM radio = TS-2000, TCP laptop1:4532
  VSPE: Splitter COM12 (WinKeyer) => COM1, COM2
     COM1 = laptop 1's N1MM WinKeyer
     TcpServer COM2 : 5555  <---- LAN -----------------  VSPE TcpClient COM2 <=> Pair <=> COM1 -> N1MM"""),
    table([["Where", "Laptop 1 (local)", "Laptop 2 (remote)"],
           ["vRadio ini", c("pcs = 2") + ", radio COM14, vfo B, dual_rx yes, midi MP3", "(no vRadio)"],
           ["VSPE", "Splitter COM12 =&gt; COM1,2; TcpServer COM2 : 5555",
            "Pair COM1 &lt;=&gt; COM2; TcpClient COM2 =&gt; laptop1:5555"],
           ["N1MM radio", "COM10, FTDX101D (VFO-A)", "SO1V, TCP, TS-2000, laptop1:4532"],
           ["N1MM radio Set", "PTT via Radio Command CW Mode, PTT Delay 50", "the same"],
           ["N1MM WinKeyer", "COM1, CW/Other ticked; DTR Always On, RTS Always Off, PTT Delay 50, WinKey, VFO Nr 1",
            "the same"],
           ["N1MM Winkey tab", "identical on both laptops", "identical on both laptops"]],
          [32 * mm, 69 * mm, 69 * mm]),
    Spacer(1, 6),
    *bullets([
        "Laptop 2 transmits on VFO-B because N1MM sends CAT " + c("TX;") + ": vRadio sends " + c("ST1;")
        + ", and after " + c("RX;") + " sends " + c("ST0;") + ".",
        "WinKeyer speed is per laptop (N1MM sends its speed with every message); mode, weighting, sidetone "
        "and PTT lead/tail are shared, so keep the Winkey tabs identical.",
        "Never send from both laptops at once: the N1MM multi-computer interlock must prevent it. "
        "Esc on either laptop cuts the message being sent.",
        "Start order: VSPE, then vRadio, then N1MM. Ports 4532 and 5555 have no password: LAN or ZeroTier only.",
    ]),
    p("microHAM Router (laptop 1)", H3),
    p("CAT COM10 38400 8N2 (N1MM radio 1), 2nd CAT COM14 38400 8N1 (vRadio), PTT COM11 RTS, "
      "Foot Switch COM13 CTS, WinKey COM12 115200 8N1 (VSPE splitter source)."),
    pic("microham_ports.png", "microHAM USB Device Router 9.3.5, micro KEYER III - Ports tab", 150 * mm),
    pic("microham_ptt.png", "microHAM Router - PTT tab", 140 * mm),
    p("VSPE (laptop 1)", H3),
    pic("vspe_laptop1.png", "VSPE on laptop 1: Splitter COM12 =&gt; COM1,2 and TcpServer COM2 : 5555", 150 * mm),
    p("N1MM (laptop 1)", H3),
    pic("n1mm_laptop1_radio.png", "N1MM laptop 1 - radio COM10 Set: PTT via Radio Command CW Mode, PTT Delay 50",
        80 * mm),
    pic("n1mm_laptop1_winkeyer.png", "N1MM laptop 1 - WinKeyer on COM1 (VSPE splitter end) and its Set", 150 * mm),
    p("Laptop 2 uses the same radio Set and WinKeyer Set; its radio row is TCP, TS-2000, laptop1:4532. "
      "Full details and checks: " + c("SETUP_2PC.md") + "."),
]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.grey)
    canvas.drawString(20 * mm, 10 * mm, "vRadio - FTDX101D as TS-2000 for N1MM")
    canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                        topMargin=16 * mm, bottomMargin=18 * mm, title="vRadio Manual",
                        author="vRadio", subject="FTDX101D to Kenwood TS-2000 translator for N1MM")
doc.build(story, onFirstPage=footer, onLaterPages=footer)
print("written", OUT)
