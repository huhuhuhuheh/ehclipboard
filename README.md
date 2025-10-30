<div align="center">
  <img width="64" height="64" alt="eh's clipboard Icon" src="https://github.com/user-attachments/assets/eef0b081-0c8f-49b9-9691-29660199aa82" />
  <h1>Eh's clipboard</h1>
  <i>Icon by <a href="https://fonts.google.com/icons">Google Fonts</a></i><p>
    
  </p>
<a href="https://github.com/huhuhuhuheh/ehclipboard/releases">
  <img src="https://img.shields.io/github/v/release/huhuhuhuheh/ehclipboard" alt="Latest Release"></a>
    <a href="#"><img alt="winget package" src="https://img.shields.io/winget/v/Eh.clipboard?label=winget"></a>
  <h2>Where to install</h2>
  <p>Either one you can grab it from the <a href="https://github.com/huhuhuhuheh/ehclipboard/releases">releases</a> tab</p>
  <p>or if you really want, you can well uhh install from your terminal i guess</p>
<table>
  <tr>
    <td align="center">
      <strong>Winget</strong>
      <pre><code>winget install Eh.clipboard</code></pre>
    </td>
  </tr>
</table>

<p>Or you can run from the <a href="#compiling">Python script itself</a></p>
</div>

<br>


<div align="center">
  <p>Simple program on a python file that alerts you what has been copied, because i was bored and i did this lmao, but also to change their things (Kinda how android tells smt has been copied to the clipboard)</p>
  <img width="398" height="126" alt="eh's clipboard Screenshot" src="https://github.com/user-attachments/assets/e7694d66-9ce9-431b-b519-c18704fe82c8" />
<h1 id="compiling">Compiling/Running From Python (Source)</h1>
The program has been built with python 3.13 (3.13.7) inside of a windows computer, so you may need to a windows machine if you want to run from the script

You need:
- [Git](https://git-scm.com/install/windows) (To be able to fork)
- A windows 10/11 computer (for python 3.13)
- [Python 3.13.7](https://www.python.org/downloads/release/python-3137/) (Optional, if you want to match with the source)


After installing the listed depdencies, open a terminal and fork the project (Or by going to Code --> Download ZIP):

```bash
git clone https://github.com/huhuhuhuheh/ehclipboard.git
```

<i>Note: If you want to fork from a version in specific download the source code from that version on the releases tab and follow the depdencies instruction from that version</i>

After forking the repo and then going to the directory, install the depdencies on your terminal before running:
```
pip install pyperclip pystray Pillow PySide6
```

And finally run the script with:

```
python clipboard.py
```

Done! You did it, you managed to ran the program from the python (soruce)!

Now you can go ahead to go to [get started](https://github.com/huhuhuhuheh/ehclipboard/wiki/How-to-use-the-program) sorta guide on github i guess

<i>Note: this does not work on linux, this is windows only, i will not make a linux port otherwise someone does it</i>

</div>
