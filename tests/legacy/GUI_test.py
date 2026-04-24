from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QComboBox, QPushButton, QMessageBox

app = QApplication([])

w = QWidget()
layout = QVBoxLayout(w)

def on_change():
    x = combo.currentIndex()
    print('---',x,'---')


combo = QComboBox()
combo.addItems(["One", "Two", "Three"])
combo.currentIndexChanged.connect(on_change)



def show_message():
    QMessageBox.information(w, "Info", "Button Clicked!")

btn = QPushButton("Show MessageBox")
btn.clicked.connect(show_message)

layout.addWidget(combo)
layout.addWidget(btn)

w.show()
app.exec()
