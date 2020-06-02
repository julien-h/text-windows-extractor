# -*- coding: utf-8 -*-
import sys
from pathlib import Path

import PyQt5
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

# ----------------------------------

import time
import itertools
import bs4
import re

def extract_text_windows(
    logfn, 
    outputfn,
    input_directory, 
    word, 
    before, 
    after,
    second_word = None,
    between = None,
    exact_match = False,
    running = lambda: True,
    ):

    word = word.lower()
    second_word = second_word.lower() if second_word else None
    before = max(before, 0)
    after = max(after, 0)
    between = max(between, 0) if between else None

    logfn('Extraction started.')
    input_directory = Path(input_directory)

    files = itertools.chain(
        input_directory.glob('**/*.html'), 
        input_directory.glob('**/*.txt'),
        input_directory.glob('**/*.md'),
        input_directory.glob('**/*.mkd')
    )
    files = list(files)
    logfn(f'Found {len(files)} to process. This may take a while.\n')
    
    def match(word, text_word):
        if exact_match:
            return word.lower() == text_word.lower()
        else:
            return word.lower() in text_word.lower()

    def find_window(i_start, words):
        i_word = i_start + before
        if i_word >= len(words):
            return None
        if second_word: # look for two-words windows
            if match(word, words[i_word]):
                w1, w2 = word, second_word
            elif match(second_word, words[i_word]):
                w1, w2 = second_word, word
            else:
                return None
            for j_word in range(i_word+1, i_word + between + 1):
                if j_word < len(words) and match(w2, words[j_word]):
                    # two-words window matched!
                    window_end = j_word + after + 1
                    return ' '.join(words[i_start: window_end])
        else: # look for single-word windows
            if match(word, words[i_word]):
                i_end = i_start + before + after + 1 
                return ' '.join(words[i_start: i_end])
        
    counter = {}
    for filepath in files:
        if not running():
            logfn('Interrupted.')
            return
        try:
            if filepath.suffix in ['.txt', '.md', '.mkd']:
                text = filepath.open('r', encoding="utf8").read()
            elif filepath.suffix == '.html':
                html = filepath.open('r', encoding="utf8").read()
                soup = bs4.BeautifulSoup(html)
                # for some reason these tags are not removed by .get_text()...
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text()
            else:
                logfn(f'Format unknown: {str(filepath)}. Skipped.')
                continue

            logfn(f'\nProcessing {str(filepath)}')
            words = text.split()
            for i_start in range(len(words)):
                if not running():
                    logfn('Interrupted.')
                    return
                window = find_window(i_start, words)
                if window:
                    logfn(window)
                    counter.setdefault(window, 0)
                    counter[window] += 1
        finally:
            pass

    logfn('\n\nResults:')
    counts_words = [(v, k) for (k, v) in counter.items()]
    counts_words = list(reversed(sorted(counts_words)))
    if not counts_words:
        logfn('Not match found.')
    for (count, word) in counts_words:
        line = f'{count:>4}:   {word}'
        logfn(line)
        outputfn(line)

    logfn('Extraction done.')


# ----------------------------------


def docs_path():
    docs = PyQt5.QtCore.QStandardPaths.writableLocation(PyQt5.QtCore.QStandardPaths.DocumentsLocation)
    return Path(docs)


class Worker(QThread):
    finished = pyqtSignal()
    logger = pyqtSignal(str)
    interrupt = pyqtSignal()

    def __init__(self, parent, callback, output_file, *args, **kwargs):
        QThread.__init__(self, parent)
        self.callback = callback
        self.output_file = output_file
        self.args = args
        self.kwargs = kwargs
        self.interrupt.connect(self.stop_running)

    @pyqtSlot()
    def stop_running(self):
        self.running = False

    def run(self):
        self.running = True
        logfn = self.logger.emit
        try:
            if self.output_file:
                Path(self.output_file).parent.mkdir(exist_ok=True, parents=True)
                output_fileobj = open(self.output_file, 'w', encoding="utf8")
                def output_fn(text):
                    output_fileobj.write(text + '\n')
            else:
                output_fileobj = None
                def output_fn(text):
                    pass

            self.callback(
                *self.args, 
                logfn=logfn, 
                outputfn=output_fn,
                running=lambda: self.running, 
                **self.kwargs
            )
            logfn('Terminated.')
        except Exception as e:
            logfn(f'\nFatal error:')
            logfn(f'{str(e)}')
        finally:
            if output_fileobj:
                output_fileobj.close()
            self.finished.emit()


def main():
    app = QApplication([])
    window = QWidget()
    window.setWindowTitle('Text Extractor')
    window.setMinimumWidth(500)
    layout = QVBoxLayout()

    # --- description ---
    descr_text = QLabel()
    descr_text.setWordWrap(True)
    descr_text.setText(
    "Information: this program extracts text-windows in a corpus of text files or html files.\n"
    "For instance, in the previous sentence, \"in a corpus of\" is a window around the word \"a\". The window starts 1 word before and ends 2 words after.\n"
    )
    layout.addWidget(descr_text)

    # --- input directory ---
    layout.addWidget(QLabel('Directory where to read files:'))
    dir_row = QHBoxLayout()
    input_folder = QLineEdit()
    dir_row.addWidget(input_folder)
    layout.addLayout(dir_row)
    browse_btn1 = QPushButton('browse')

    @pyqtSlot()
    def on_browse_clicked1():
        path = QFileDialog.getExistingDirectory(window, "Select Input Directory", str(docs_path()))
        if path:
            path = str(path)
            input_folder.setText(path)

    browse_btn1.clicked.connect(on_browse_clicked1)
    dir_row.addWidget(browse_btn1)

    # --- output directory ---
    layout.addWidget(QLabel('Directory where to write results:'))
    output_dir_row = QHBoxLayout()
    output_folder = QLineEdit()
    output_folder.setText(str(docs_path() / 'text-window.txt'))
    output_dir_row.addWidget(output_folder)
    
    @pyqtSlot()
    def on_browse_clicked2():
        path = QFileDialog.getSaveFileName(window, "Choose Output file", str(docs_path()))
        if path and path[0]:
            path = str(path[0])
            output_folder.setText(path)

    browse_btn2 = QPushButton('browse')
    browse_btn2.clicked.connect(on_browse_clicked2)
    output_dir_row.addWidget(browse_btn2)
    layout.addLayout(output_dir_row)

    # --- parameters ---

    word_input_row_layout = QHBoxLayout()
    #
    word_input_label = QLabel('word:')
    word_input = QLineEdit()
    word1_row_layout = QHBoxLayout()
    word1_row_layout.addWidget(word_input_label)
    word1_row_layout.addWidget(word_input)
    word1_row_layout.addSpacing(0)
    word1_row_layout.addStretch(0)
    word_input_row_layout.addLayout(word1_row_layout)
    #
    second_word_label = QLabel('second word:')
    second_word_input = QLineEdit()
    word2_row_layout = QHBoxLayout()
    word2_row_layout.addWidget(second_word_label)
    word2_row_layout.addWidget(second_word_input)
    word2_row_layout.addSpacing(0)
    word2_row_layout.addStretch(0)
    word_input_row_layout.addLayout(word2_row_layout)
    def hide_second_word(disabled):
        second_word_input.setDisabled(disabled)
    
    count_row = QHBoxLayout()
    #
    words_before = QSpinBox();
    words_before.setMinimum(0);
    words_before.setSingleStep(1);
    words_before.setValue(2);
    words_before_row = QHBoxLayout()
    words_before_row.addWidget(QLabel('Before:'))
    words_before_row.addWidget(words_before)
    words_before_row.addStretch(0)
    words_before_row.addSpacing(0)
    count_row.addLayout(words_before_row)
    #
    words_between = QSpinBox();
    words_between.setMinimum(0);
    words_between.setSingleStep(1);
    words_between.setValue(2);
    between_label = QLabel('Between:')
    between_layout = QHBoxLayout()
    between_layout.addWidget(between_label)
    between_layout.addWidget(words_between)
    between_layout.addStretch(0)
    between_layout.addSpacing(0)
    count_row.addLayout(between_layout)
    def hide_between_count(disabled):
        words_between.setDisabled(disabled)
    #
    words_after = QSpinBox();
    words_after.setMinimum(0);
    words_after.setSingleStep(1);
    words_after.setValue(2);
    words_after_layout = QHBoxLayout()
    words_after_layout.addWidget(QLabel('After:'))
    words_after_layout.addWidget(words_after)
    words_after_layout.addStretch(0)
    words_after_layout.addSpacing(0)
    count_row.addLayout(words_after_layout)
    
    # --- mode ---
    @pyqtSlot()
    def on_activated(item):
        if 'single word' in item:
            hide_second_word(True)
            hide_between_count(True)
        elif 'two words' in item:
            hide_second_word(False)
            hide_between_count(False)
        else:
            on_output(f'[ERROR] Unknown mode: {item}')

    combo_row = QHBoxLayout()
    combo_row.addWidget(QLabel('Extraction mode:'))
    combo = QComboBox()
    combo.addItem("Window around a single word")
    combo.addItem("Window around two words")
    combo.activated[str].connect(on_activated)
    combo_row.addWidget(combo)
    combo_row.addSpacing(0)
    combo_row.addStretch(0)

    match_row = QHBoxLayout()
    match_label = QLabel('Exact match')
    match_box = QCheckBox()
    match_row.addWidget(match_label)
    match_row.addWidget(match_box)
    match_row.addStretch(0)
    match_row.addSpacing(0)

    combo_match_row = QHBoxLayout()
    combo_match_row.addLayout(combo_row)
    combo_match_row.addLayout(match_row)

    layout.addLayout(combo_match_row)
    layout.addLayout(word_input_row_layout)
    layout.addLayout(count_row)
    hide_between_count(True)
    hide_second_word(True)

    # --- action buttons ---
    go_btn = QPushButton('Go!')
    cancel_btn = QPushButton('Cancel')
    cancel_btn.setDisabled(True)
    output_text = QPlainTextEdit()
    global logfn
    logfn = output_text.appendPlainText
    worker = None

    def set_ui_enabled(enabled):
        input_folder.setEnabled(enabled)
        output_folder.setEnabled(enabled)
        browse_btn1.setEnabled(enabled)
        browse_btn2.setEnabled(enabled)
        go_btn.setEnabled(enabled)
        combo.setEnabled(enabled)
        match_box.setEnabled(enabled)
        word_input.setEnabled(enabled)
        second_word_input.setEnabled(enabled)
        words_after.setEnabled(enabled)
        words_between.setEnabled(enabled)
        words_before.setEnabled(enabled)
        #
        cancel_btn.setDisabled(enabled)
        #
        if enabled:
            on_activated(combo.currentText())
        

    @pyqtSlot()
    def on_output(output):
        output_text.appendPlainText(output)
        output_text.ensureCursorVisible()

    @pyqtSlot()
    def on_cancel():
        go_btn.setDisabled(False)
        cancel_btn.setDisabled(True)
        on_output('Canceling tasks, please wait...')
        global worker
        worker.interrupt.emit()
        # Note: worker.finished will re-enable UI

    @pyqtSlot()
    def on_start():
        if not input_folder.text().strip():
            on_output('Please provide an input folder')
            return
        if not output_folder.text().strip():
            on_output('Please enter path where to save results')
            return

        set_ui_enabled(False)
        print('Go! button clicked: input={input_folder.text()}, output={output_folder.text()}')
        
        global worker
        single_word_mode = 'single word' in combo.currentText()
        worker = Worker(window, 
            callback=extract_text_windows,
            input_directory=input_folder.text(),
            output_file=output_folder.text(),
            word=word_input.text(),
            before=words_before.value(),
            after=words_after.value(),
            second_word = second_word_input.text() if not single_word_mode else None,
            between = words_between.value() if not single_word_mode else None,
            exact_match = match_box.isChecked(),
        )
        worker.logger.connect(on_output)
        worker.finished.connect(lambda: set_ui_enabled(True))
        worker.start()

    cancel_btn.clicked.connect(on_cancel)
    go_btn.clicked.connect(on_start)

    actions_layout = QHBoxLayout()
    actions_layout.addWidget(go_btn)
    actions_layout.addWidget(cancel_btn)
    layout.addLayout(actions_layout)
    layout.addWidget(output_text)

    window.setLayout(layout)
    window.show()
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())