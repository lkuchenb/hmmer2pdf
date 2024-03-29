![release badge](https://img.shields.io/github/v/release/lkuchenb/hmmer2pdf?sort=semver)

# hmmer2pdf

![hmmer2pdf example output](img/hmmer2pdf_example.png?raw=true "hmmer2pdf example output")

## Features

 * Match and insert state color encodes emission entropy
 * Line width encodes transition probability
 * Emission probability tables for emitting states (*insert* and *match*)

## Installation

    pip install git+https://github.com/lkuchenb/hmmer2pdf@latest

## Usage

    hmmer2pdf < input.hmm > output.pdf

## Requirements

 * Python 3.x
 * LaTeX suite with the `tikz` and `standalone` packages installed
 * `lualatex` in your `PATH`
