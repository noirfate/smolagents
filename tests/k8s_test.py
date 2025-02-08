from kubernetes import client, config

def main():
    # 如果在本地运行，加载本地的 kubeconfig 文件
    # 如果脚本在 Pod 内运行，则可以调用 config.load_incluster_config()
    config.load_kube_config()

    # 创建一个 CoreV1Api 实例，用于操作核心 API
    v1 = client.CoreV1Api()

    # 获取并打印节点列表
    print("------ 节点列表 ------")
    node_list = v1.list_node()
    for node in node_list.items:
        print(node.metadata.name)

    # 获取并打印所有命名空间下的 Pod 列表
    print("\n------ Pod 列表 ------")
    pod_list = v1.list_pod_for_all_namespaces()
    for pod in pod_list.items:
        print(f"Namespace: {pod.metadata.namespace} - Name: {pod.metadata.name}")

if __name__ == '__main__':
    main()