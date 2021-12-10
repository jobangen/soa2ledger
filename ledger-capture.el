;;; ledger-capture.el --- Functions to maintain a zettel-archive -*- lexical-binding: t -*-

;; Copyright (C) 2021 Jan Ole Bangen (jobangen AT gmail DOT com).

;; Package-Requires: ledger-mode

;; This file is not part of GNU Emacs.

;; This file is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation; either version 3, or (at your option)
;; any later version.

;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; For a full copy of the GNU General Public License
;; see <http://www.gnu.org/licenses/>.

;;; Commentary:
;;
;; Mode for editing ledger entries. Derived from ledger-mode.
;;
;;; Code:
(require 'ledger-mode)

(defun ledger-capture-finalize ()
  "Finalize edited entry."
  (interactive)
  (ledger-post-align-dwim)
  (ledger-toggle-current-transaction)
  (goto-char (point-min))
  (flush-lines "^;")
  (save-buffer)
  (server-edit))

(defun ledger-capture-abort ()
  "Abort capture of ledger entry."
  (interactive)
  (erase-buffer)
  (save-buffer)
  (server-edit))

(defun ledger-capture-setup ()
  "Preprocess ledger entry in capture buffer."
  (interactive)
  (ledger-navigate-next-uncleared)
  (while (search-forward "???" nil t)
    (replace-match "")))

(defvar ledger-capture-mode-map nil "Keymap for `ledger-capture-mode-mode'.")

(progn
  (setq ledger-capture-mode-map (make-sparse-keymap))
  (define-key ledger-capture-mode-map (kbd "C-c C-c") 'ledger-capture-finalize)
  (define-key ledger-capture-mode-map (kbd "C-c C-k") 'ledger-capture-abort))


(define-derived-mode ledger-capture-mode ledger-mode "Ledger Cap"
  (ledger-capture-setup))

(add-to-list 'auto-mode-alist '("\\.ledger-cap\\'" . ledger-capture-mode))

(provide 'ledger-capture)

;;; ledger-capture.el ends here
