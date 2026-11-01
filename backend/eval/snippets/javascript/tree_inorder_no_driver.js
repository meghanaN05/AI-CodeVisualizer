/**
 * Definition for a binary tree node.
 * function TreeNode(val, left, right) {
 *     this.val = (val===undefined ? 0 : val)
 *     this.left = (left===undefined ? null : left)
 *     this.right = (right===undefined ? null : right)
 * }
 */
var inorderTraversal = function(root) {
    const res = [];
    const go = (node) => {
        if (!node) return;
        go(node.left);
        res.push(node.val);
        go(node.right);
    };
    go(root);
    return res;
};
