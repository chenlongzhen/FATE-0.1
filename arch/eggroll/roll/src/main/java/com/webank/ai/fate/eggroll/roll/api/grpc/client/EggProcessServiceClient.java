/*
 * Copyright 2019 The FATE Authors. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.webank.ai.fate.eggroll.roll.api.grpc.client;

import com.webank.ai.fate.api.eggroll.processor.ProcessServiceGrpc;
import com.webank.ai.fate.api.eggroll.processor.Processor;
import com.webank.ai.fate.api.eggroll.storage.Kv;
import com.webank.ai.fate.api.eggroll.storage.StorageBasic;
import com.webank.ai.fate.core.api.grpc.client.GrpcAsyncClientContext;
import com.webank.ai.fate.core.api.grpc.client.GrpcCalleeStreamingStubMethodInvoker;
import com.webank.ai.fate.core.api.grpc.client.GrpcStreamingClientTemplate;
import com.webank.ai.fate.core.constant.RuntimeConstants;
import com.webank.ai.fate.core.model.DelayedResult;
import com.webank.ai.fate.core.model.impl.SingleDelayedResult;
import com.webank.ai.fate.core.utils.TypeConversionUtils;
import com.webank.ai.fate.eggroll.meta.service.dao.generated.model.Node;
import com.webank.ai.fate.eggroll.roll.api.grpc.observer.processor.egg.EggProcessorReduceResponseStreamObserver;
import com.webank.ai.fate.eggroll.roll.api.grpc.observer.processor.egg.EggProcessorUnaryProcessToStorageLocatorResponseObserver;
import com.webank.ai.fate.eggroll.roll.factory.RollModelFactory;
import com.webank.ai.fate.eggroll.roll.factory.RollProcessorServiceCallModelFactory;
import com.webank.ai.fate.eggroll.roll.service.model.OperandBroker;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

import java.lang.reflect.InvocationTargetException;

@Component
@Scope("prototype")
public class EggProcessServiceClient {
    @Autowired
    private RollProcessorServiceCallModelFactory rollProcessorServiceCallModelFactory;
    @Autowired
    private TypeConversionUtils typeConversionUtils;
    @Autowired
    private RollModelFactory rollModelFactory;

    public StorageBasic.StorageLocator map(Processor.UnaryProcess request, Node node) {
        return unaryProcessToStorageLocatorUnaryCall(request, node, ProcessServiceGrpc.ProcessServiceStub::map);
    }

    public StorageBasic.StorageLocator mapValues(Processor.UnaryProcess request, Node node) {
        return unaryProcessToStorageLocatorUnaryCall(request, node, ProcessServiceGrpc.ProcessServiceStub::mapValues);
    }

    public StorageBasic.StorageLocator join(Processor.BinaryProcess request, Node node) {
        GrpcAsyncClientContext<ProcessServiceGrpc.ProcessServiceStub, Processor.BinaryProcess, StorageBasic.StorageLocator> context
                = rollProcessorServiceCallModelFactory.createBinaryProcessToStorageLocatorContext();

        DelayedResult<StorageBasic.StorageLocator> delayedResult = new SingleDelayedResult<>();

        context.setLatchInitCount(1)
                .setEndpoint(typeConversionUtils.toEndpoint(node))
                .setFinishTimeout(RuntimeConstants.DEFAULT_WAIT_TIME, RuntimeConstants.DEFAULT_TIMEUNIT)
                .setCalleeStreamingMethodInvoker(ProcessServiceGrpc.ProcessServiceStub::join)
                .setCallerStreamObserverClassAndArguments(EggProcessorUnaryProcessToStorageLocatorResponseObserver.class, delayedResult);

        GrpcStreamingClientTemplate<ProcessServiceGrpc.ProcessServiceStub, Processor.BinaryProcess, StorageBasic.StorageLocator> template
                = rollProcessorServiceCallModelFactory.createBinaryProcessToStorageLocatorTemplate();
        template.setGrpcAsyncClientContext(context);

        StorageBasic.StorageLocator result = null;

        try {
            result = template.calleeStreamingRpcWithImmediateDelayedResult(request, delayedResult);
        } catch (InvocationTargetException e) {
            throw new RuntimeException(e);
        }

        return result;
    }

    public OperandBroker reduce(Processor.UnaryProcess request, Node node) {
        OperandBroker result = rollModelFactory.createOperandBroker();
        GrpcAsyncClientContext<ProcessServiceGrpc.ProcessServiceStub, Processor.UnaryProcess, Kv.Operand> context
                = rollProcessorServiceCallModelFactory.createUnaryProcessToOperandContext();

        context.setLatchInitCount(1)
                .setEndpoint(typeConversionUtils.toEndpoint(node))
                .setFinishTimeout(RuntimeConstants.DEFAULT_WAIT_TIME, RuntimeConstants.DEFAULT_TIMEUNIT)
                .setCalleeStreamingMethodInvoker(ProcessServiceGrpc.ProcessServiceStub::reduce)
                .setCallerStreamObserverClassAndArguments(EggProcessorReduceResponseStreamObserver.class, result);

        GrpcStreamingClientTemplate<ProcessServiceGrpc.ProcessServiceStub, Processor.UnaryProcess, Kv.Operand> template
                = rollProcessorServiceCallModelFactory.createUnaryProcessToOperandTemplate();
        template.setGrpcAsyncClientContext(context);

        template.calleeStreamingRpc(request);

        return result;
    }

    public StorageBasic.StorageLocator mapPartitions(Processor.UnaryProcess request, Node node) {
        return unaryProcessToStorageLocatorUnaryCall(request, node, ProcessServiceGrpc.ProcessServiceStub::mapPartitions);
    }

    public StorageBasic.StorageLocator glom(Processor.UnaryProcess request, Node node) {
        return unaryProcessToStorageLocatorUnaryCall(request, node, ProcessServiceGrpc.ProcessServiceStub::glom);
    }

    public StorageBasic.StorageLocator sample(Processor.UnaryProcess request, Node node) {
        return unaryProcessToStorageLocatorUnaryCall(request, node, ProcessServiceGrpc.ProcessServiceStub::sample);
    }

    private StorageBasic.StorageLocator
    unaryProcessToStorageLocatorUnaryCall(Processor.UnaryProcess request,
                                          Node node,
                                          GrpcCalleeStreamingStubMethodInvoker<
                                                  ProcessServiceGrpc.ProcessServiceStub,
                                                  Processor.UnaryProcess,
                                                  StorageBasic.StorageLocator> calleeStreamingStubMethodInvoker) {
        GrpcAsyncClientContext<ProcessServiceGrpc.ProcessServiceStub, Processor.UnaryProcess, StorageBasic.StorageLocator> context
                = rollProcessorServiceCallModelFactory.createUnaryProcessToStorageLocatorContext();

        DelayedResult<StorageBasic.StorageLocator> delayedResult = new SingleDelayedResult<>();

        context.setLatchInitCount(1)
                .setEndpoint(typeConversionUtils.toEndpoint(node))
                .setFinishTimeout(RuntimeConstants.DEFAULT_WAIT_TIME, RuntimeConstants.DEFAULT_TIMEUNIT)
                .setCalleeStreamingMethodInvoker(calleeStreamingStubMethodInvoker)
                .setCallerStreamObserverClassAndArguments(EggProcessorUnaryProcessToStorageLocatorResponseObserver.class, delayedResult);

        GrpcStreamingClientTemplate<ProcessServiceGrpc.ProcessServiceStub, Processor.UnaryProcess, StorageBasic.StorageLocator> template
                = rollProcessorServiceCallModelFactory.createUnaryProcessToStorageLocatorTemplate();
        template.setGrpcAsyncClientContext(context);

        StorageBasic.StorageLocator result = null;

        try {
            result = template.calleeStreamingRpcWithImmediateDelayedResult(request, delayedResult);
        } catch (InvocationTargetException e) {
            throw new RuntimeException(e);
        }

        return result;
    }
}
