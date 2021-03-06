# Copyright (c) 2020 Leon Kuchenbecker <leon.kuchenbecker@uni-tuebingen.de>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import re
import collections
import tempfile
import shutil
import os
import subprocess
import math
import argparse

# CONSTANTS ########################################################################################

latex_header = """\\documentclass[tikz,crop,10pt]{standalone}
\\usetikzlibrary{positioning}
\\usetikzlibrary{matrix}
\\usetikzlibrary{arrows.meta}
\\usetikzlibrary{shapes.geometric}
\\newlength\\hdist
\\newlength\\vdist
\\newlength\\lwidth
\\setlength\\hdist{1mm}
\\setlength\\vdist{1mm}
\\setlength\\lwidth{.0125mm}
\\colorlet{mcolor}{orange}
\\colorlet{icolor}{green}
\\begin{document}
    \\begin{tikzpicture}\n"""


tikz_settings = """    [
    % Overall settings
    every node/.append style={scale=0.05},
    font=\small,
    line width=.0125mm,
    % Probability text nodes
    prob/.style={inner sep=.5mm, fill=white, midway},
    loopprob/.style={prob, above=.03mm},
    dprob/.style={prob, near end},
    % General states
    state/.style={minimum size=2.0em, inner sep=0mm, draw},
    % General emitting states
    emitting/.style={state, circle},
    % General non-emitting states
    nonemitting/.style={state, diamond},
    % m-state settings
    mstate/.style={emitting, minimum size=2.0em},
    % i-state settings
    istate/.style={emitting},
    % d-state settings
    dstate/.style={nonemitting, fill=red},
    % Arrows
    arr/.tip={Triangle[scale=.1]},
    % Transitions
    trans/.style=[-arr],
    ]"""


# TYPE DEFINITIONS #################################################################################

SubHMM = collections.namedtuple('SubHMM', ['m_em', 'ins_em','trans', 'm_ent', 'ins_ent'])
HMM = collections.namedtuple('HMM', ['subs', 'norm_m_ent', 'norm_ins_ent'])

class HMMParseException(RuntimeError):
    pass

class LaTeXException(RuntimeError):
    pass

class NoLaTeXException(RuntimeError):
    pass

# FUNCTION DEFINITIONS #############################################################################

def ent(x):
    """ Entropy [bits] given a vector of log probabilities """
    x     = [ math.exp(-val) for val in x ]
    logs  = [ math.log(val, 2) for val in x ]
    prods = [ a * b for a,b in zip(x, logs) ]
    return - sum(prods)

def parseMatchEmProbs(s, m_num):
    """ Parses a match state emission probability row in the hmmer hmm file format """
    #                           m_num      aa em probs...  MAP.... CONS.......  RF.......... MM.. CS..........
    alph_size=None
    if re.match('^ +' + str(m_num) + '( +\d+[.]\d+){20} +(\d+|-) ([a-zA-Z.]|-) ([a-zA-Z.]|-) [m-] ([a-zA-Z.]|-)$', s):
        alph_size = 20 # Protein
    elif re.match('^ +' + str(m_num) + '( +\d+[.]\d+){4} +(\d+|-) ([a-zA-Z.]|-) ([a-zA-Z.]|-) [m-] ([a-zA-Z.]|-)$', s):
        alph_size = 4  # DNA
    else:
        raise HMMParseException("Match state pos " + str(m_num) + ": Invalid emission probablity string: '" + s + "'")
    return [ float(val) for val in s.split()[1:(alph_size+1)] ]

def parseInsEmProbs(s):
    """ Parses a insert state emission probability row in the hmmer hmm file format """
    if not any([
        re.match('^ +( +\d+[.]\d+){20}$', s), # Protein
        re.match('^ +( +\d+[.]\d+){4}$', s),  # DNA
        ]):
        raise HMMParseException("Invalid insertion state emission probablity string: '" + s + "'")
    return [ float(val) for val in s.split() ]

def parseTransProbs(s):
    """ Parses a transition probability row in the hmmer hmm file format """
    if not re.match('^ +( +\d+[.]\d+){2} +(\d+[.]\d+|[*])( +\d+[.]\d+){3} +(\d+[.]\d+|[*])$', s):
        raise HMMParseException("Invalid transition probablity string: '" + s + "'")
    return [ (lambda v : float('inf') if v=='*' else float(v))(val) for val in s.split() ]

def rescale(subs, getter):
    """ Rescales values across all subs, getter defines which member to rescale """
    vals = [ getter(sub) for sub in subs ]
    min_val = min([val for val in vals if not val is None])
    max_val = max([val for val in vals if not val is None])
    val_range = max_val - min_val if max_val != min_val else 1
    res = [ (lambda x:None if x is None else (x - min_val) / (val_range))(val) for val in vals ]
    return res

def parseHMMFile(instream):
    """ Parses a hmmer HMM file given a file input object """
    subs = list()
    in_hmm = False
    raw = [ line.rstrip('\n') for line in instream ]

    # Read the begin state insert emission and transition probabilities
    gen = (i for i in range(len(raw)))
    for i in gen:
        line = raw[i]
        if re.match('^HMM\s+A\s+', line):
            next(gen)
            in_hmm = True
            continue
        if in_hmm:
            if re.match('^\s+COMPO\s+', line):
                i += 1
            ins_em   = parseInsEmProbs(raw[i])
            subs += [ SubHMM(None, ins_em, parseTransProbs(raw[i+1]), None, ent(ins_em)) ]
            i += 2
            break

    hmm_position = 1
    for i in range(i, len(raw), 3):
        if re.match('^//', raw[i]):
            break
        match_em = parseMatchEmProbs(raw[i], hmm_position)
        ins_em   = parseInsEmProbs(raw[i+1])
        subs += [ SubHMM(match_em, ins_em, parseTransProbs(raw[i+2]), ent(match_em), ent(ins_em)) ]
        hmm_position += 1
    return HMM(subs, rescale(subs, lambda x : x.m_ent), rescale(subs, lambda x : x.ins_ent))

def openLaTeX():
    """ Create a temporary directory with a TeX file. Writes header and settings to the file. Returns file handle. """
    tdir = tempfile.mkdtemp()
    out = open(tdir + '/hmm.tex', 'w')
    out.write(latex_header)
    out.write(tikz_settings)
    return tdir, out

def closeLaTeX(out):
    """ Write the footer and close the TeX output file. """
    out.write('    \\end{tikzpicture}\n\end{document}\n')
    out.close()

def drawTrans(out, hmm, pos):
    """ Draw the state transition arcs for the states correspoding to position 'pos' """
    vals  = [ math.exp(-val) for val in hmm[pos].trans ]
    lw_co = [ 1 + 2 * val for val in vals ]
    if not vals[0] is None and vals[0] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[0]) + '\\lwidth] (m' + str(pos) + ') -- (m'  + str(pos+1) + ') node [prob] {$' + "%.3f" % vals[0] + '$};\n')
    if not vals[1] is None and vals[1] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[1]) + '\\lwidth] (m' + str(pos) + ') -- (i'  + str(pos) + ') node [prob] {$' + "%.3f" % vals[1] + '$};\n')
    if not vals[2] is None and vals[2] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[2]) + '\\lwidth] (m' + str(pos) + ') -- (d'  + str(pos+1) + ') node [dprob] {$' + "%.3f" % vals[2] + '$};\n')
    if not vals[3] is None and vals[3] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[3]) + '\\lwidth] (i' + str(pos) + ') -- (m'  + str(pos+1) + ') node [prob] {$' + "%.3f" % vals[3] + '$};\n')
    if not vals[4] is None and vals[4] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[4]) + '\\lwidth] (i' + str(pos) + ') to [out=60,in=120,looseness=8] node [loopprob] {$' + "%.3f" % vals[4] + '$} (i'  + str(pos) + ') ;\n')
    if not vals[5] is None and vals[5] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[5]) + '\\lwidth] (d' + str(pos) + ') -- (m'  + str(pos+1) + ') node [dprob] {$' + "%.3f" % vals[5] + '$};\n')
    if not vals[6] is None and vals[6] > 0:
        out.write('        \\draw [trans, line width=' + str(lw_co[6]) + '\\lwidth] (d' + str(pos) + ') -- (d'  + str(pos+1) + ') node [prob] {$' + "%.3f" % vals[6] + '$};\n')

def draw_eprobs(out, hmm, pos, getter, pos_string, color):
    """ Draw the state emission probability tables for the states correspoding
    to position 'pos'. 'getter' defines whether insert oder match states are
    drawn."""
    probs        = [ math.exp(-val) for val in getter(hmm.subs[pos]) ]
    prob_strings = [ "%.3f" % val for val in probs ]
    prob_colors  = [ color + '!' + str(math.floor(100*val)) for val in probs ]

    if len(probs)==20:
        out.write("""
        \\matrix [inner sep=.05mm, outer sep=0pt, """ + pos_string + str(pos) + """, matrix of nodes, nodes={inner sep=.2mm, font=\\tiny, minimum size=1.0em}, row sep=.04mm] (m) {%
            |[circle, fill=""" + prob_colors[0] + """]|A & $""" + prob_strings[0] + """$ & |[circle, fill=""" + prob_colors[10] + """]|M & $""" + prob_strings[10] + """$\\\\
            |[circle, fill=""" + prob_colors[1] + """]|C & $""" + prob_strings[1] + """$ & |[circle, fill=""" + prob_colors[11] + """]|N & $""" + prob_strings[11] + """$\\\\
            |[circle, fill=""" + prob_colors[2] + """]|D & $""" + prob_strings[2] + """$ & |[circle, fill=""" + prob_colors[12] + """]|P & $""" + prob_strings[12] + """$\\\\
            |[circle, fill=""" + prob_colors[3] + """]|E & $""" + prob_strings[3] + """$ & |[circle, fill=""" + prob_colors[13] + """]|Q & $""" + prob_strings[13] + """$\\\\
            |[circle, fill=""" + prob_colors[4] + """]|F & $""" + prob_strings[4] + """$ & |[circle, fill=""" + prob_colors[14] + """]|R & $""" + prob_strings[14] + """$\\\\
            |[circle, fill=""" + prob_colors[5] + """]|G & $""" + prob_strings[5] + """$ & |[circle, fill=""" + prob_colors[15] + """]|S & $""" + prob_strings[15] + """$\\\\
            |[circle, fill=""" + prob_colors[6] + """]|H & $""" + prob_strings[6] + """$ & |[circle, fill=""" + prob_colors[16] + """]|T & $""" + prob_strings[16] + """$\\\\
            |[circle, fill=""" + prob_colors[7] + """]|I & $""" + prob_strings[7] + """$ & |[circle, fill=""" + prob_colors[17] + """]|V & $""" + prob_strings[17] + """$\\\\
            |[circle, fill=""" + prob_colors[8] + """]|K & $""" + prob_strings[8] + """$ & |[circle, fill=""" + prob_colors[18] + """]|W & $""" + prob_strings[18] + """$\\\\
            |[circle, fill=""" + prob_colors[9] + """]|L & $""" + prob_strings[9] + """$ & |[circle, fill=""" + prob_colors[19] + """]|Y & $""" + prob_strings[19] + """$\\\\
        };
        \\draw [rounded corners=.1mm] (m.south west) rectangle (m.north east);\n""")
    elif len(probs)==4:
        out.write("""
        \\matrix [inner sep=.05mm, outer sep=0pt, """ + pos_string + str(pos) + """, matrix of nodes, nodes={inner sep=.2mm, font=\\tiny, minimum size=1.0em}, row sep=.04mm] (m) {%
            |[circle, fill=""" + prob_colors[0] + """]|A & $""" + prob_strings[0] + """$ \\\\
            |[circle, fill=""" + prob_colors[1] + """]|C & $""" + prob_strings[1] + """$ \\\\
            |[circle, fill=""" + prob_colors[2] + """]|G & $""" + prob_strings[2] + """$ \\\\
            |[circle, fill=""" + prob_colors[3] + """]|T & $""" + prob_strings[3] + """$ \\\\
        };
        \\draw [rounded corners=.1mm] (m.south west) rectangle (m.north east);\n""")


def drawPosition(out, hmm, pos):
    """ Draw the state nodes and emission probability tables for position 'pos' """
    # Anti proportional, relative entropy - low entropy -> high color intensity
    mfill = 'gray!50'
    if pos==0:
        mtext = 'B'
    elif pos==len(hmm.subs):
        mtext = 'E'
    else:
        mtext = '$m_{' + str(pos) + '}$'
        mfill = 'mcolor!' + str(math.floor(100 * (1-hmm.norm_m_ent[pos])))
    node_pos = '' if pos==0 else ', right=\\hdist of m' + str(pos-1)
    out.write('        \\node[mstate, fill=' + mfill + node_pos + '] (m' + str(pos) + ') {' + mtext + '};\n')
    if pos<len(hmm.subs):
        ifill = 'icolor!' + str(math.floor(100 * (1-hmm.norm_ins_ent[pos])))
        out.write('        \\node[istate, fill = ' + ifill + ', above right=\\vdist and .5\\hdist of m' + str(pos) + '] (i' + str(pos) + ') {$i_{' + str(pos) +'}$};\n')
        out.write('        \\node[dstate, below=\\vdist of m' + str(pos) + '] (d' + str(pos) + ') {$d_{' + str(pos) + '}$};\n')

    if pos > 0 and pos<len(hmm.subs):
        draw_eprobs(out, hmm, pos, lambda x : x.m_em, "below=1.8mm of m", "mcolor")
    if pos<len(hmm.subs):
        draw_eprobs(out, hmm, pos, lambda x : x.ins_em, "above=.8mm of i", "icolor")

def drawHMM(out, hmm):
    """ Draw an HMM given the output file object 'out' and 'hmm' """
    for pos in range(1+len(hmm.subs)):
        drawPosition(out, hmm, pos)
    for pos in range(0, len(hmm.subs)):
        drawTrans(out, hmm.subs, pos)

def checkLaTeX(pdflatex):
    """ Check if 'lualatex' can be executed and raise an exception otherwise """
    compiler = 'pdflatex' if pdflatex else 'lualatex'
    try:
        ret = subprocess.run([compiler, '--version'], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    except FileNotFoundError:
        raise NoLaTeXException()
    if ret.returncode != 0:
        raise NouaLaTeXException()

def compileLaTeX(tdir, pdflatex):
    """ Compile the 'hmm.tex' file in the given directory """
    compiler = 'pdflatex' if pdflatex else 'lualatex'
    ret = subprocess.run([compiler, '--interaction', 'batchmode', 'hmm'], cwd = tdir, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    if ret.returncode != 0:
        raise LaTeXException

def remove_temp_dir(tdir, **kwargs):
    """ Remove the temporary directory """
    print("Cleaning up temporary data.", file = sys.stderr)
    shutil.rmtree(tdir, kwargs)

# MAIN PROGRAM #####################################################################################

def get_config():
    parser = argparse.ArgumentParser("hmmer2pdf", description="Plotting tool for HMMER3 hmm files based on TikZ")
    parser.add_argument('infile', type = argparse.FileType('r'), nargs="?", default = sys.stdin, help = "The input HMM file to read from. Default: stdin")
    parser.add_argument('outfile', type = argparse.FileType('w'), nargs="?", default = sys.stdout, help = "The output PDF file to write to. Default: stdout")
    parser.add_argument('--pdflatex', action='store_true', help = "Use 'pdflatex' instead of 'lualatex'. WARNING - 'pdflatex' will fail on larger HMMS due to memory limits")
    return parser.parse_args()

def main():
    try:
        args = get_config()
        tdir = str()

        # Warn user if pdflatex switch was used
        if args.pdflatex:
            print("WARNING - pdflatex will only work on small HMMs.", file = sys.stderr)

        # Check latex compiler availablilty
        checkLaTeX(args.pdflatex)

        print("Reading HMM file...", file = sys.stderr, end = '', flush = True)
        # Parse the HMM
        hmm = parseHMMFile(args.infile)

        # Start a LaTeX document
        tdir, out = openLaTeX()

        print(" Done.\nLaTeX Conversion...", file = sys.stderr, end = '')
        # Draw the HMM
        drawHMM(out, hmm)

        # Close the LaTeX document
        closeLaTeX(out)

        print(" Done.\nCompiling...", file = sys.stderr, end = '')
        # Compile the LaTeX document
        compileLaTeX(tdir, args.pdflatex)

        print(" Done.", file = sys.stderr)
        # Copy the temporary PDF file to stdout
        shutil.copyfileobj(open(tdir + '/hmm.pdf', 'rb'), args.outfile.buffer)

        # Remove temporary files
        remove_temp_dir(tdir)
    except NoLaTeXException:
        compiler = 'pdflatex' if args.pdflatex else 'lualatex'
        print(f"\nERROR - Could not execute '{compiler}' - Do you have a LaTeX suite installed?", file = sys.stderr)
    except KeyboardInterrupt:
        print("\nUser interrupted.", file = sys.stderr)
        if tdir:
            remove_temp_dir(tdir, ignore_errors = True)
    except HMMParseException as err:
        print("\nERROR - Failed to parse hmm file format:", err, file = sys.stderr)
    except LaTeXException:
        print("\nERROR - LaTeX compiler failed. You may want to inspect the .log and .tex files in\n" + tdir, file = sys.stderr)
    except Exception:
        print("\n****************************************************************************************************", file = sys.stderr)
        print("UNEXPECTED ERROR - Please report this error at https://github.com/lkuchenb/hmmer2pdf/issues and", file = sys.stderr)
        print("keep the contents of '" + tdir + "' and the\ntraceback below for debugging purposes.", file = sys.stderr)
        print("****************************************************************************************************", file = sys.stderr)
        raise
