# hmmer2pdf

![hmmer2pdf example output](img/hmmer2pdf_example.png?raw=true "hmmer2pdf example output")

## Features

 * Match state node color encodes emission entropy
 * Line width encodes transition probability
 * Emission probability tables for emitting states (*insert* and *match*)

## Usage

```
hmmer2pdf < input.hmm > output.pdf
```

## Requirements

 * Python 3.x
 * LaTeX suite
 * `lualatex` in your `PATH`
