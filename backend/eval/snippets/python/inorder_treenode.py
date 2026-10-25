class TreeNode:
    def __init__(self, val, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


def inorder(root, out):
    if root is None:
        return
    inorder(root.left, out)
    out.append(root.val)
    inorder(root.right, out)


root = TreeNode(8, TreeNode(3, TreeNode(1), TreeNode(6)), TreeNode(10))
result = []
inorder(root, result)
print(result)
