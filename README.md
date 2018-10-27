# hmmer2pdf

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
