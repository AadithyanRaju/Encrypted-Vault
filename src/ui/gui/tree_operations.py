"""Tree widget operations for the GUI application."""
from pathlib import Path

try:
    from PyQt6 import QtWidgets, QtCore
except ImportError:
    pass


def populate_tree(tree_widget, inner_metadata, set_descendants_checked_callback):
    """Populate tree widget with files from vault metadata.
    
    Args:
        tree_widget: QTreeWidget to populate
        inner_metadata: Vault metadata containing files list
        set_descendants_checked_callback: Function to set descendants checked state
    """
    tree_widget.clear()
    # Build folder structure from relpaths
    folders = {}
    for f in inner_metadata.files:
        relpath = f.get("relpath") or f.get("name", "")
        parts = Path(relpath).parts
        parent = tree_widget.invisibleRootItem()
        current_path = []
        # Create/find folder nodes
        for part in parts[:-1]:
            current_path.append(part)
            key = "/".join(current_path)
            if key not in folders:
                item = QtWidgets.QTreeWidgetItem(["", "", part, "", "/".join(current_path)])
                item.setFirstColumnSpanned(False)
                folders[key] = item
                parent.addChild(item)
                # Add checkbox to folder node and wire it to toggle descendants
                folder_checkbox = QtWidgets.QCheckBox()
                # Keep small margins so nested indentation doesn't hide the widget
                folder_checkbox.setStyleSheet("margin-left:4px; margin-right:4px;")
                tree_widget.setItemWidget(item, 0, folder_checkbox)
                # Capture current item in a closure
                def make_handler(folder_item):
                    def handler(state):
                        set_descendants_checked_callback(folder_item, state == QtCore.Qt.CheckState.Checked)
                    return handler
                folder_checkbox.stateChanged.connect(make_handler(item))
            parent = folders[key]
        # Add file leaf
        leaf = QtWidgets.QTreeWidgetItem(["", f.get("id", ""), f.get("name", ""), str(f.get("size", 0)), relpath])
        parent.addChild(leaf)
        # Add a checkbox widget on column 0
        checkbox = QtWidgets.QCheckBox()
        checkbox.setStyleSheet("margin-left:4px; margin-right:4px;")
        tree_widget.setItemWidget(leaf, 0, checkbox)


def filter_tree_items(tree_widget, search_text):
    """Filter tree items based on search text.
    
    Args:
        tree_widget: QTreeWidget to filter
        search_text: Text to search for in file names and paths
    """
    search_text = search_text.lower().strip()
    
    # If search is empty, show all items
    if not search_text:
        it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
        while it.value():
            item = it.value()
            item.setHidden(False)
            it += 1
        return
    
    # First pass: collect matching files and their parent folders
    # Use a set of object IDs for O(1) lookup (QTreeWidgetItems aren't hashable)
    items_to_show_ids = set()
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        # Files have an ID in column 1, folders have empty string
        if item.text(1):  # This is a file
            # Get file name and relpath for matching
            file_name = item.text(2).lower()
            file_relpath = item.text(4).lower()
            
            # Check if search text matches name or relpath
            if search_text in file_name or search_text in file_relpath:
                # Mark this file and all parent folders to be shown
                items_to_show_ids.add(id(item))
                parent = item.parent()
                while parent is not None:
                    items_to_show_ids.add(id(parent))
                    parent = parent.parent()
        it += 1
    
    # Second pass: show/hide all items based on the collected IDs
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        item.setHidden(id(item) not in items_to_show_ids)
        it += 1


def set_descendants_checked(tree_widget, item, checked):
    """Recursively set all descendant file checkboxes.
    
    Args:
        tree_widget: QTreeWidget containing the item
        item: QTreeWidgetItem whose descendants to check/uncheck
        checked: bool, True to check, False to uncheck
    """
    for i in range(item.childCount()):
        child = item.child(i)
        cb = tree_widget.itemWidget(child, 0)
        if cb is not None:
            cb.setChecked(checked)
        # Recurse into folders
        if child.childCount() > 0:
            set_descendants_checked(tree_widget, child, checked)


def clear_all_checkboxes(tree_widget):
    """Clear all checkboxes in the tree.
    
    Args:
        tree_widget: QTreeWidget to clear checkboxes in
    """
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        cb = tree_widget.itemWidget(item, 0)
        if cb is not None:
            # Use setChecked to update UI; connected handlers will run as expected
            cb.setChecked(False)
        it += 1


def select_all_items(tree_widget):
    """Select all files in the tree.
    
    Args:
        tree_widget: QTreeWidget to select all items in
    """
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        checkbox = tree_widget.itemWidget(item, 0)
        if checkbox:
            checkbox.setChecked(True)
        it += 1


def deselect_all_items(tree_widget):
    """Deselect all files in the tree.
    
    Args:
        tree_widget: QTreeWidget to deselect all items in
    """
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        checkbox = tree_widget.itemWidget(item, 0)
        if checkbox:
            checkbox.setChecked(False)
        it += 1


def get_selected_files(tree_widget):
    """Get list of selected file IDs and names.
    
    Args:
        tree_widget: QTreeWidget to get selections from
        
    Returns:
        list of tuples: [(file_id, file_name, file_relpath), ...]
    """
    selected = []
    it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
    while it.value():
        item = it.value()
        checkbox = tree_widget.itemWidget(item, 0)
        # only leaves have IDs
        if checkbox and checkbox.isChecked() and item.text(1):
            selected.append((item.text(1), item.text(2), item.text(4)))
        it += 1
    return selected


def handle_tree_item_clicked(tree_widget, item, column, last_clicked_item, set_descendants_checked_callback):
    """Handle clicks on tree rows for selection.
    
    Args:
        tree_widget: QTreeWidget
        item: QTreeWidgetItem that was clicked
        column: int, column index that was clicked
        last_clicked_item: Previously clicked item for shift-range selection
        set_descendants_checked_callback: Function to set descendants checked state
        
    Returns:
        QTreeWidgetItem: Updated last_clicked_item
    """
    try:
        if item is None:
            return last_clicked_item

        modifiers = QtWidgets.QApplication.keyboardModifiers()

        # Clicking the checkbox column should preserve default multi-select checkbox behavior
        if column == 0:
            # update last clicked item for shift-range behavior
            return item

        # Ctrl+click: toggle the clicked row's checkbox without changing others
        if modifiers & QtCore.Qt.KeyboardModifier.ControlModifier:
            cb = tree_widget.itemWidget(item, 0)
            if cb is not None:
                cb.setChecked(not cb.isChecked())
            return item

        # Shift+click: select a contiguous range from last clicked item to this one
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier and last_clicked_item is not None:
            # Build a flat list of tree items in visual order
            items = []
            it = QtWidgets.QTreeWidgetItemIterator(tree_widget)
            while it.value():
                items.append(it.value())
                it += 1

            try:
                i1 = items.index(last_clicked_item)
                i2 = items.index(item)
            except ValueError:
                # Fallback to single selection if items can't be located
                i1 = i2 = None

            if i1 is None or i2 is None:
                # fallback single select
                clear_all_checkboxes(tree_widget)
                cb = tree_widget.itemWidget(item, 0)
                if cb is not None:
                    cb.setChecked(True)
                return item

            start, end = sorted((i1, i2))
            clear_all_checkboxes(tree_widget)
            for idx in range(start, end + 1):
                it_item = items[idx]
                if it_item.childCount() != 0:
                    # folder: check its checkbox and all descendants
                    folder_cb = tree_widget.itemWidget(it_item, 0)
                    if folder_cb is not None:
                        folder_cb.setChecked(True)
                    set_descendants_checked_callback(it_item, True)
                else:
                    cb = tree_widget.itemWidget(it_item, 0)
                    if cb is not None:
                        cb.setChecked(True)

            return item

        # Default (no modifiers): single-select the clicked item or folder contents
        if item.childCount() != 0:
            # folder node clicked (non-checkbox column): select all descendants
            clear_all_checkboxes(tree_widget)
            folder_cb = tree_widget.itemWidget(item, 0)
            if folder_cb is not None:
                folder_cb.setChecked(True)
            set_descendants_checked_callback(item, True)
            return item

        # Leaf item clicked normally: clear others and check this one only
        clear_all_checkboxes(tree_widget)
        cb = tree_widget.itemWidget(item, 0)
        if cb is not None:
            cb.setChecked(True)
        return item
    except Exception:
        # Non-critical UI handler: ignore unexpected errors
        return last_clicked_item
