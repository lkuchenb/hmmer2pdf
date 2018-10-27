# Example

## Compilation:
```
hmmer2pdf hmmer2pdf_example.hmm > hmmer2pdf_example.pdf
```
`hmmer2pdf` produces rather small PDF pages to overcome hard TeX limitations
(maximum dimensions) when handling large HMMs. To scale the file up to a decent
size you can use
```
pdfjam --outfile hmmer2pdf_example.pdf --papersize '{10in,6in}' --scale .9 hmmer2pdf_example.pdf
```
`pdfjam` is part of the TeX Live.
